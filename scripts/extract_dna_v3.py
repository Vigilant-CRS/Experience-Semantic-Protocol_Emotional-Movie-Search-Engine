"""
DNA-Extractor V3 — extracts ontology-v3 DNA per film via OpenAI Chat API.

Output JSONL: one line per film with fields
  tmdb_id, title, year, raw_llm, dna_v3
where dna_v3 contains L1-normalized weighted dicts per bucket.

Usage:
  venv/bin/python3 scripts/extract_dna_v3.py --pilot              # 5 test films
  venv/bin/python3 scripts/extract_dna_v3.py --limit 100          # first 100
  venv/bin/python3 scripts/extract_dna_v3.py                      # all
  venv/bin/python3 scripts/extract_dna_v3.py --workers 20         # parallelism
"""
import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
ONT_DIR = ROOT / "config" / "ontology_v3"
DATA_DIR = ROOT / "data"
SOURCE = ROOT / "movies_export.json"
OUT = DATA_DIR / "movies_dna_v3.jsonl"
ERR = DATA_DIR / "movies_dna_v3.errors.jsonl"

OPENAI_MODEL = os.getenv("OPENAI_MODEL_DNA", "gpt-5.4-mini")
OPENAI_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"


# GPT-5 / o-series use max_completion_tokens and reject custom temperature
def _is_new_model(name: str) -> bool:
    return ("gpt-5" in name) or name.startswith("o3") or name.startswith("o4") or name.startswith("o1")


class QuotaExhausted(RuntimeError):
    """Raised when the OpenAI account has insufficient quota — retry is futile."""


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_ontology() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in ["emotions", "wirkung", "plot_themes", "genres",
                 "settings", "archetypes", "moods", "pacing",
                 "content_features", "subjects"]:
        path = ONT_DIR / f"{name}.json"
        if path.exists():
            out[name] = json.load(open(path))["tags"]
        else:
            out[name] = []  # graceful: missing optional bucket = empty
    out["definitions"] = json.load(open(ONT_DIR / "tag_definitions.json"))["definitions"]
    out["synonyms"] = json.load(open(ONT_DIR / "synonyms.json"))["groups"]
    return out


def build_system_prompt(ont: Dict[str, Any]) -> str:
    """Static system prompt — eligible for OpenAI prompt caching."""
    defs = ont["definitions"]

    def fmt(tags: List[str]) -> str:
        return "\n".join(f"  - {t}: {defs.get(t, '?')}" for t in tags)

    return f"""You are a film-DNA extractor. Given a film's title, year, overview, keywords and TMDB genres, you output a structured DNA in JSON.

CRITICAL RULES:
1. Use ONLY the canonical tags from the lists below. No new terms.
2. Each block (emotions+wirkung, themes+genres, setting, mood, pacing) is a weighted dict where weights sum to ~1.0 (don't worry about exact normalization — code will renormalize).
3. Use 3-7 tags per block. Don't fill all of them. Pick the most defining.
4. archetype is a SINGLE value from the archetype list.
5. protagonist_gender is one of: male, female, ensemble, non_binary.
6. Return strict JSON only.

== EMOTIONS (Plutchik 8 families × 3 intensities, 24 tags) ==
{fmt(ont['emotions'])}

== WIRKUNG (viewer impact, 6 tags) ==
{fmt(ont['wirkung'])}

== PLOT_THEMES (35 tags) ==
{fmt(ont['plot_themes'])}

== GENRES (TMDB feature-film, 18 tags — distribute weights across genres that fit, even if TMDB only labels 1-2) ==
{fmt(ont['genres'])}

== SETTINGS (15 tags) ==
{fmt(ont['settings'])}

== ARCHETYPES (10 tags, pick ONE) ==
{fmt(ont['archetypes'])}

== MOODS (12 tags) ==
{fmt(ont['moods'])}

== PACING (8 tags) ==
{fmt(ont['pacing'])}

== CONTENT FEATURES ({len(ont['content_features'])} tags — content/violence advisories, only set when prominently present) ==
{fmt(ont['content_features'])}

== SUBJECTS ({len(ont['subjects'])} tags — what the film is ABOUT topically; only set when CENTRAL to the film) ==
{fmt(ont['subjects'])}

== OUTPUT SCHEMA ==
{{
  "emotions":   {{"tag": weight, ...}},     // 3-6 entries from emotions list
  "wirkung":    {{"tag": weight, ...}},     // 1-3 entries from wirkung list
  "themes":     {{"tag": weight, ...}},     // 3-6 entries from plot_themes list
  "genres":     {{"tag": weight, ...}},     // 1-3 entries from genres list (use TMDB genres as starting point)
  "setting":    {{"tag": weight, ...}},     // 1-2 entries from settings list
  "archetype":  "tag",                       // SINGLE value from archetypes list
  "mood":       {{"tag": weight, ...}},     // 1-3 entries from moods list
  "pacing":     {{"tag": weight, ...}},     // 1-2 entries from pacing list
  "content_features": {{"tag": weight, ...}}, // 0-5 entries — only PROMINENTLY featured content
  "subjects":   {{"tag": weight, ...}},     // 0-3 entries — only CENTRAL subjects (a Mafia film
                                             // gets {{"mafia": 1.0}}; a thriller with one mob scene gets {{}})
  "protagonist_gender": "male|female|ensemble|non_binary"
}}

== FEW-SHOT EXAMPLE ==
INPUT:
title: "John Wick"
year: 2014
tmdb_genres: ["Action", "Thriller"]
overview: "An ex-hit-man comes out of retirement to track down the gangsters that killed his dog and took everything from him."
keywords: ["assassin", "revenge", "dog", "hitman", "new york"]

OUTPUT:
{{
  "emotions": {{"rage": 0.3, "grief": 0.25, "anticipation": 0.2, "dread": 0.15, "frustration": 0.1}},
  "wirkung":  {{"cathartic": 0.7, "haunting": 0.3}},
  "themes":   {{"revenge": 0.5, "grief_and_loss": 0.2, "underdog_triumph": 0.15, "betrayal": 0.15}},
  "genres":   {{"Action": 0.6, "Thriller": 0.3, "Crime": 0.1}},
  "setting":  {{"urban_modern": 0.7, "criminal_underworld": 0.3}},
  "archetype": "antihero",
  "mood":     {{"dark": 0.5, "gritty": 0.3, "noir": 0.2}},
  "pacing":   {{"action_packed": 0.7, "fast_paced": 0.3}},
  "protagonist_gender": "male"
}}
"""


def build_user_prompt(film: Dict[str, Any]) -> str:
    title = film.get("title") or film.get("original_title") or "?"
    year = film.get("year") or (film.get("release_date", "")[:4] or "?")
    overview = (film.get("overview") or "").strip()
    keywords = film.get("keywords") or []
    genres = film.get("genres") or []
    director = film.get("director") or ""

    return f"""title: {title!r}
year: {year}
tmdb_genres: {json.dumps(genres)}
director: {director!r}
overview: {overview!r}
keywords: {json.dumps(keywords[:15])}

Extract the DNA. Return strict JSON, no markdown."""


def normalize_l1(d: Dict[str, float]) -> Dict[str, float]:
    if not isinstance(d, dict) or not d:
        return {}
    s = sum(float(v) for v in d.values() if isinstance(v, (int, float)) and v > 0)
    if s <= 0:
        return {}
    return {k: float(v) / s for k, v in d.items()
            if isinstance(v, (int, float)) and v > 0}


def filter_to_canonical(d: Dict[str, float], allowed: List[str],
                        synonyms: Dict[str, List[str]]) -> Dict[str, float]:
    """Keep only canonical tags. Map synonyms to canonical heads."""
    if not isinstance(d, dict):
        return {}
    syn_to_canonical = {}
    for canon, syns in synonyms.items():
        if canon in allowed:
            for s in syns:
                syn_to_canonical[s.lower()] = canon
    out: Dict[str, float] = {}
    for k, v in d.items():
        if not isinstance(v, (int, float)) or v <= 0:
            continue
        kk = k.strip()
        if kk in allowed:
            out[kk] = out.get(kk, 0.0) + float(v)
        else:
            mapped = syn_to_canonical.get(kk.lower())
            if mapped and mapped in allowed:
                out[mapped] = out.get(mapped, 0.0) + float(v) * 0.7  # synonym decay
    return out


def normalize_dna(raw: Dict[str, Any], ont: Dict[str, Any]) -> Dict[str, Any]:
    syns = ont["synonyms"]
    # emotion_sparse = emotions + wirkung, jointly L1-normalized
    emo = filter_to_canonical(raw.get("emotions", {}), ont["emotions"], syns)
    wir = filter_to_canonical(raw.get("wirkung", {}), ont["wirkung"], syns)
    emotion_sparse = normalize_l1({**emo, **wir})

    # theme_sparse = themes + genres, jointly L1-normalized
    th = filter_to_canonical(raw.get("themes", {}), ont["plot_themes"], syns)
    gn = filter_to_canonical(raw.get("genres", {}), ont["genres"], syns)
    theme_sparse = normalize_l1({**th, **gn})

    setting = normalize_l1(filter_to_canonical(raw.get("setting", {}), ont["settings"], syns))
    mood = normalize_l1(filter_to_canonical(raw.get("mood", {}), ont["moods"], syns))
    pacing = normalize_l1(filter_to_canonical(raw.get("pacing", {}), ont["pacing"], syns))
    content_features = normalize_l1(filter_to_canonical(
        raw.get("content_features", {}), ont["content_features"], syns))
    subjects = normalize_l1(filter_to_canonical(
        raw.get("subjects", {}), ont["subjects"], syns))

    archetype = raw.get("archetype")
    if archetype not in ont["archetypes"]:
        archetype = None

    gender = (raw.get("protagonist_gender") or "").lower()
    if gender not in {"male", "female", "ensemble", "non_binary"}:
        gender = None

    return {
        "emotion_sparse": emotion_sparse,    # L1=1, dim=30
        "theme_sparse": theme_sparse,        # L1=1 (plot_themes+genres jointly)
        "setting": setting,                   # part of theme_sparse vector at indices 53-67
        "archetype": archetype,               # payload, single value
        "mood": mood,                         # part of theme_sparse vector at indices 68-79
        "pacing": pacing,                     # part of theme_sparse vector at indices 80-87
        "subjects": subjects,                 # part of theme_sparse vector at indices 88+ (extension)
        "content_features": content_features, # payload, NOT in any sparse vector
        "protagonist_gender": gender,         # payload
    }


_session = None
_lock = threading.Lock()


def get_session() -> requests.Session:
    global _session
    with _lock:
        if _session is None:
            _session = requests.Session()
        return _session


def call_openai(system: str, user: str, max_retries: int = 6) -> Dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    is_new = _is_new_model(OPENAI_MODEL)
    payload: Dict[str, Any] = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        ("max_completion_tokens" if is_new else "max_tokens"): 1500,
        "response_format": {"type": "json_object"},
    }
    if not is_new:
        payload["temperature"] = 0.1
    last_err = "unknown"
    text = ""
    for attempt in range(max_retries):
        try:
            r = get_session().post(OPENAI_URL, headers=headers, json=payload, timeout=120)
            # Distinguish insufficient_quota from rate_limit (both are HTTP 429)
            if r.status_code == 429:
                try:
                    err = r.json().get("error", {})
                    err_type = err.get("type", "")
                    err_code = err.get("code", "") or ""
                except Exception:
                    err_type, err_code = "", ""
                if err_type == "insufficient_quota" or "quota" in err_code:
                    raise QuotaExhausted(
                        f"OpenAI quota exhausted (type={err_type}, code={err_code}) — top up account, retrying is futile."
                    )
                wait = int(r.headers.get("Retry-After", "0")) or (2 ** attempt + 3)
                last_err = f"429 rate-limit ({err_type or 'transient'}), wait {wait}s (attempt {attempt+1}/{max_retries})"
                time.sleep(min(wait, 60))
                continue
            if r.status_code in (500, 502, 503, 504):
                last_err = f"server {r.status_code}"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            return json.loads(text)
        except QuotaExhausted:
            raise
        except json.JSONDecodeError as e:
            last_err = f"JSON decode: {e} -- text was: {text[:200]}"
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            last_err = f"request: {e}"
            time.sleep(2 ** attempt)
        except Exception as e:
            last_err = f"unexpected: {type(e).__name__}: {e}"
            time.sleep(1 + attempt)
    raise RuntimeError(f"openai failed after {max_retries} retries: {last_err}")


_LOCAL_CALL = None  # set by main() when --local-llm is passed


def call_local(system: str, user: str, max_retries: int = 3) -> Dict[str, Any]:
    """Local Qwen (GGUF) drop-in for call_openai. Returns parsed JSON dict."""
    from scripts.llm_local import chat_complete
    last_err = "unknown"
    for attempt in range(max_retries):
        try:
            text = chat_complete(system, user, max_tokens=1500, temperature=0.1)
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_err = f"JSON decode: {e} -- text was: {text[:200] if 'text' in dir() else '<none>'}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.5)
    raise RuntimeError(f"local LLM failed after {max_retries} retries: {last_err}")


def extract_one(film: Dict[str, Any], system: str, ont: Dict[str, Any]) -> Dict[str, Any]:
    user = build_user_prompt(film)
    caller = _LOCAL_CALL or call_openai
    raw = caller(system, user)
    dna = normalize_dna(raw, ont)
    return {
        "tmdb_id": film["tmdb_id"],
        "title": film.get("title"),
        "year": film.get("year"),
        "dna_v3": dna,
        "raw_llm": raw,  # keep raw for debugging
    }


def main():
    global _LOCAL_CALL
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="run on 5 hand-picked test films")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--out", type=str, default=str(OUT))
    ap.add_argument("--source", type=str, default=str(SOURCE),
                    help="path to film JSON list (default: movies_export.json)")
    ap.add_argument("--local-llm", action="store_true",
                    help="use local Qwen GGUF via llama-cpp instead of OpenAI")
    ap.add_argument("--llm-size", default="4b", choices=["2b", "4b"],
                    help="local LLM size when --local-llm is set")
    args = ap.parse_args()

    load_env()
    ont = load_ontology()
    system = build_system_prompt(ont)
    print(f"System prompt: {len(system)} chars (~{len(system)//4} tokens)")

    if args.local_llm:
        os.environ["LOCAL_LLM_SIZE"] = args.llm_size
        os.environ.setdefault("LOCAL_LLM_N_GPU_LAYERS", "999")
        os.environ.setdefault("LOCAL_LLM_CTX", "4096")
        _LOCAL_CALL = call_local
        # Pre-warm the model so we fail fast on missing GGUF / OOM
        from scripts.llm_local import get_llm
        get_llm()
        if args.workers > 1:
            print(f"WARN: --local-llm forces single-thread; ignoring --workers {args.workers}")
            args.workers = 1
        print(f"Mode: LOCAL Qwen-{args.llm_size}, workers=1")
    else:
        print(f"Mode: OpenAI ({OPENAI_MODEL}), workers={args.workers}")

    movies = json.load(open(args.source))
    by_id = {m["tmdb_id"]: m for m in movies}

    if args.pilot:
        # John Wick, Amélie, Devil's Advocate, Shawshank, Get Out
        pilot_ids = [245891, 194, 1813, 278, 419430]
        targets = [by_id[i] for i in pilot_ids if i in by_id]
        out_path = ROOT / "data" / "movies_dna_v3.pilot.jsonl"
    else:
        targets = list(movies)
        if args.limit:
            targets = targets[: args.limit]
        out_path = Path(args.out)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    done_ids = set()
    if args.resume and out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                done_ids.add(json.loads(line)["tmdb_id"])
            except Exception:
                pass

    todo = [m for m in targets if m["tmdb_id"] not in done_ids and m.get("overview")]
    print(f"Total films: {len(targets)}  Already done: {len(done_ids)}  To extract: {len(todo)}")

    if not todo:
        print("Nothing to do.")
        return

    written = 0
    errors = 0
    quota_killed = False
    t0 = time.time()
    write_lock = threading.Lock()
    with open(out_path, "a") as f_out, open(ERR, "a") as f_err:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(extract_one, m, system, ont): m for m in todo}
            for fut in as_completed(futures):
                film = futures[fut]
                try:
                    rec = fut.result()
                    with write_lock:
                        f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        f_out.flush()
                    written += 1
                except QuotaExhausted as e:
                    quota_killed = True
                    print(f"\n!!! QUOTA EXHAUSTED — stopping immediately. Top up OpenAI account.\n!!! {e}", flush=True)
                    # Cancel all remaining futures
                    for f in futures:
                        f.cancel()
                    break
                except Exception as e:
                    errors += 1
                    with write_lock:
                        f_err.write(json.dumps({
                            "tmdb_id": film["tmdb_id"],
                            "title": film.get("title"),
                            "error": str(e),
                        }, ensure_ascii=False) + "\n")
                        f_err.flush()

                if (written + errors) % 25 == 0 or written + errors == len(todo):
                    elapsed = time.time() - t0
                    rate = (written + errors) / max(elapsed, 1e-3)
                    eta = (len(todo) - written - errors) / max(rate, 1e-3)
                    print(f"  [{written + errors}/{len(todo)}] ok={written} err={errors} "
                          f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    status = "QUOTA-KILLED" if quota_killed else "Done"
    print(f"\n{status}. Written: {written}  Errors: {errors}  Model: {OPENAI_MODEL}  Output: {out_path}", flush=True)


if __name__ == "__main__":
    main()
