"""
Copyright (c) 2026 Vigilant e.K. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
Minimal-invasive enrichment: ergänze fehlende `subjects` und `content_features`
Felder in movies_dna_v3.jsonl, ohne die existierende DNA anzutasten.

Hintergrund: Filme die vor der Einführung der Buckets (2026-05-06) extrahiert
wurden haben die Felder gar nicht. Statt sie komplett neu zu extrahieren
($28 für 21K), nutzen wir einen schmalen Mini-Prompt der NUR die zwei
Buckets ausfragt (~$0.0003/Film mit Prompt-Caching).

Filme die schon ein subjects-Feld haben (egal ob `{}` oder belegt) bleiben
unangetastet — der LLM hat dort bereits entschieden.

Usage:
  venv/bin/python3 scripts/enrich_subjects_content.py --dry-run         # nur zählen
  venv/bin/python3 scripts/enrich_subjects_content.py --workers 20      # echter Run
  venv/bin/python3 scripts/enrich_subjects_content.py --limit 50        # Test-Batch

Schreibt das Resultat nach movies_dna_v3.enriched.jsonl.
Replace mit: `mv data/movies_dna_v3.enriched.jsonl data/movies_dna_v3.jsonl`
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.extract_dna_v3 import (
    load_env, load_ontology, call_openai, OPENAI_MODEL,
    normalize_l1, filter_to_canonical, QuotaExhausted,
)


def build_mini_system_prompt(ont: Dict[str, Any]) -> str:
    """Mini-prompt: nur subjects + content_features Buckets."""
    defs = ont["definitions"]

    def fmt(tags: List[str]) -> str:
        return "\n".join(f"  - {t}: {defs.get(t, '?')}" for t in tags)

    return f"""You are a film-content tagger. Given a film's title, year, overview, and keywords,
output ONLY the SUBJECTS and CONTENT_FEATURES tags that apply.

CRITICAL RULES:
1. Use ONLY canonical tags from the two lists below. No new terms.
2. Subjects: 0-3 entries — only when CENTRAL to the film. A Mafia film gets
   {{"mafia": 1.0}}; a thriller with one mob scene gets {{}}.
3. Content features: 0-5 entries — only when PROMINENTLY featured.
4. If nothing fits a bucket, return an empty object {{}} for it.
5. Return strict JSON only.

== SUBJECTS ({len(ont['subjects'])} tags — what the film is ABOUT topically) ==
{fmt(ont['subjects'])}

== CONTENT FEATURES ({len(ont['content_features'])} tags — content/violence advisories) ==
{fmt(ont['content_features'])}

== OUTPUT SCHEMA ==
{{
  "subjects":         {{"tag": weight, ...}},
  "content_features": {{"tag": weight, ...}}
}}

== EXAMPLES ==
INPUT: "John Wick" (2014) genres=["Action","Thriller"] keywords=[assassin,revenge,dog,hitman,new york]
overview="An ex-hit-man comes out of retirement to track down the gangsters that killed his dog."
OUTPUT: {{"subjects": {{}}, "content_features": {{"firearms": 0.55, "physical_combat": 0.30, "graphic_violence": 0.15}}}}

INPUT: "Spectre" (2015) genres=["Action","Adventure"] keywords=[secret agent,spy,mi6,villain]
overview="A cryptic message from Bond's past sends him on a trail to uncover a sinister organization."
OUTPUT: {{"subjects": {{"espionage": 1.0}}, "content_features": {{"firearms": 0.5, "vehicular_combat": 0.3, "physical_combat": 0.2}}}}

INPUT: "Amélie" (2001) genres=["Comedy","Romance"] keywords=[paris,whimsy,quirky]
overview="A whimsical young woman in Paris decides to bring joy to the lives of those around her."
OUTPUT: {{"subjects": {{}}, "content_features": {{}}}}
"""


def build_mini_user_prompt(film: Dict[str, Any]) -> str:
    title = film.get("title") or film.get("original_title") or "?"
    year = film.get("year") or (film.get("release_date", "")[:4] or "?")
    overview = (film.get("overview") or "").strip()[:500]
    keywords = film.get("keywords") or []
    genres = film.get("genres") or []
    return f"""title: {title!r}
year: {year}
genres: {json.dumps(genres)}
keywords: {json.dumps(keywords[:10])}
overview: {overview!r}

Tag this film. Return JSON only."""


def enrich_one(rec: Dict[str, Any], films_by_id: Dict[int, Dict[str, Any]],
               system: str, ont: Dict[str, Any]) -> tuple:
    """Returns (updated_rec, status_string)."""
    tid = rec["tmdb_id"]
    film = films_by_id.get(tid)
    if not film:
        return rec, "no_metadata"
    if not film.get("overview"):
        # Set empty fields so we don't try again next run
        rec["dna_v3"].setdefault("subjects", {})
        rec["dna_v3"].setdefault("content_features", {})
        return rec, "no_overview"

    user = build_mini_user_prompt(film)
    raw = call_openai(system, user)

    syns = ont["synonyms"]
    subj_filtered = filter_to_canonical(raw.get("subjects") or {},
                                         ont["subjects"], syns)
    cf_filtered = filter_to_canonical(raw.get("content_features") or {},
                                       ont["content_features"], syns)

    rec["dna_v3"]["subjects"] = normalize_l1(subj_filtered)
    rec["dna_v3"]["content_features"] = normalize_l1(cf_filtered)
    return rec, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=str(ROOT / "data" / "movies_dna_v3.jsonl"))
    ap.add_argument("--source", default=str(ROOT / "data" / "movies_top20k.json"))
    ap.add_argument("--out", default=None,
                    help="Output JSONL (default: <jsonl>.enriched.jsonl)")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None,
                    help="Process at most N candidates (testing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Just count candidates, no API calls")
    args = ap.parse_args()

    load_env()
    ont = load_ontology()
    system = build_mini_system_prompt(ont)
    print(f"Mini-prompt size: {len(system)} chars (~{len(system)//4} tokens)")
    print(f"OpenAI model: {OPENAI_MODEL}")

    # Load film metadata for overview/keywords lookup
    films = json.load(open(args.source))
    films_by_id = {m["tmdb_id"]: m for m in films}
    print(f"Loaded {len(films_by_id)} film metadata records")

    # Read JSONL; identify candidates (missing subjects OR content_features key)
    in_path = Path(args.jsonl)
    out_path = Path(args.out) if args.out else in_path.with_suffix(".enriched.jsonl")

    all_records: List[Optional[Dict[str, Any]]] = []
    todo_idx: List[int] = []
    with open(in_path) as f:
        for i, line in enumerate(f):
            try:
                rec = json.loads(line)
                all_records.append(rec)
                dna = rec.get("dna_v3", {})
                if ("subjects" not in dna) or ("content_features" not in dna):
                    todo_idx.append(i)
            except Exception:
                all_records.append(None)

    print(f"JSONL lines: {len(all_records)}")
    print(f"Candidates (missing subjects or content_features key): {len(todo_idx)}")

    if args.limit:
        todo_idx = todo_idx[:args.limit]
        print(f"Limited to first {len(todo_idx)}")

    if args.dry_run:
        # Show distribution of candidates by vote_count
        votes_buckets = {">3000": 0, ">500": 0, ">100": 0, "<=100": 0, "no_meta": 0}
        for idx in todo_idx:
            rec = all_records[idx]
            tid = rec["tmdb_id"]
            m = films_by_id.get(tid, {})
            if not m:
                votes_buckets["no_meta"] += 1
                continue
            v = m.get("vote_count", 0) or 0
            if v > 3000: votes_buckets[">3000"] += 1
            elif v > 500: votes_buckets[">500"] += 1
            elif v > 100: votes_buckets[">100"] += 1
            else: votes_buckets["<=100"] += 1
        print("Candidate vote_count distribution:")
        for k, v in votes_buckets.items():
            print(f"  {k}: {v}")
        # Cost estimate
        cost = len(todo_idx) * 0.00028
        print(f"\nEstimated cost: ~${cost:.2f}")
        print(f"Estimated time @ 20 workers, 2s/call: ~{len(todo_idx)*2/20/60:.0f} min")
        return

    written = 0
    errors = 0
    quota_killed = False
    t0 = time.time()
    write_lock = threading.Lock()

    def _process(idx: int) -> tuple:
        rec = all_records[idx]
        result = enrich_one(rec, films_by_id, system, ont)
        return idx, result

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_process, idx): idx for idx in todo_idx}
        for fut in as_completed(futures):
            try:
                idx, (rec, status) = fut.result()
                with write_lock:
                    all_records[idx] = rec
                if status == "ok":
                    written += 1
                else:
                    errors += 1
            except QuotaExhausted as e:
                quota_killed = True
                print(f"\n!!! QUOTA EXHAUSTED — stopping. {e}", flush=True)
                for f in futures:
                    f.cancel()
                break
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)

            if (written + errors) % 50 == 0 or (written + errors) == len(todo_idx):
                elapsed = time.time() - t0
                rate = (written + errors) / max(elapsed, 1e-3)
                eta = (len(todo_idx) - written - errors) / max(rate, 1e-3)
                print(f"  [{written+errors}/{len(todo_idx)}] ok={written} err={errors} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    # Write enriched JSONL
    with open(out_path, "w") as f:
        for rec in all_records:
            if rec is not None:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    status_label = "QUOTA-KILLED" if quota_killed else "Done"
    print(f"\n{status_label}. Written: {written}  Errors: {errors}")
    print(f"Output: {out_path}")
    print(f"Replace original: mv {out_path} {in_path}")


if __name__ == "__main__":
    main()
