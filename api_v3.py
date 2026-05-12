"""
MindRead V3 API — schlanker Endpoint auf der V3-Pipeline.

Endpoints:
  GET  /api/health            — Status
  GET  /api/film/{tmdb_id}    — Film-Details inkl. DNA
  POST /api/search            — Hauptendpoint
  GET  /api/ontology          — verfügbare Tags pro Bucket (für Wheel-UI)

POST /api/search Body (alle Felder optional):
  {
    "similar_to": 245891,           // ODER
    "query": "düstere Rachefilme",  // (eines von beiden Pflicht)
    "limit": 10,

    "w_synopsis": 0.5,              // Slider: Plot-Ähnlichkeit
    "w_emotion": 0.3,               // Slider: Emotional fit
    "w_theme": 0.2,                 // Slider: Thema/Genre
    "indie_mainstream": 0.0,        // -1.0 indie ↔ +1.0 mainstream

    "year_min": 1990, "year_max": 2024,
    "runtime_min": 60, "runtime_max": 240,
    "min_vote_count": 50,
    "genre": ["Action", "Thriller"],          // hard filter
    "gender": "male"                          // male|female|ensemble|non_binary
  }

Run with: venv/bin/python3 -m uvicorn api_v3:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import os
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Make sure CPU-only before torch import
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from scripts.search_v3 import (
    load_indices, to_sparse, manual_weighted_fusion,
    encode_query_text, COLLECTION,
)
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue, MatchAny, Range,
)
from qdrant_client import QdrantClient
import requests
import json
from scripts.extract_dna_v3 import (
    build_system_prompt, load_ontology, normalize_dna,
    normalize_l1, load_env, OPENAI_MODEL,
)

LOCAL_LLM_ENABLED = os.environ.get("LOCAL_LLM_ENABLED", "0") == "1"

# Tenant-level provider whitelist — when deployed for a customer, restrict UI/filter
# to only their providers. Empty/unset = all providers exposed.
# Example: TENANT_PROVIDERS_ALLOWED="Magenta TV,Netflix"
_tenant_raw = os.environ.get("TENANT_PROVIDERS_ALLOWED", "").strip()
TENANT_PROVIDERS_ALLOWED = [p.strip() for p in _tenant_raw.split(",") if p.strip()] if _tenant_raw else []

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("mindread.v3")

load_env()

# ─── globals ──────────────────────────────────────────────────────────────
ONT = load_ontology()
EMOTION_IDX, THEME_IDX = load_indices()
SYSTEM_PROMPT = build_system_prompt(ONT)
QDRANT = QdrantClient(host=os.getenv("QDRANT_HOST", "localhost"),
                      port=int(os.getenv("QDRANT_PORT", "6333")), timeout=30.0)
QDRANT_URL = f"http://{os.getenv('QDRANT_HOST','localhost')}:{os.getenv('QDRANT_PORT','6333')}"

# Title→tmdb_id cache (built at startup, used by similar_to_title resolution)
TITLE_INDEX: Dict[str, int] = {}     # lowercase title → tmdb_id
TITLE_PAYLOADS: Dict[int, Dict[str, Any]] = {}  # tmdb_id → small payload

# Tag-Listen für Ontologie-Endpoint
ONTOLOGY_BUCKETS = {
    "emotions": ONT["emotions"],
    "wirkung": ONT["wirkung"],
    "plot_themes": ONT["plot_themes"],
    "genres": ONT["genres"],
    "settings": ONT["settings"],
    "archetypes": ONT["archetypes"],
    "moods": ONT["moods"],
    "pacing": ONT["pacing"],
    "subjects": ONT.get("subjects", []),
    "content_features": ONT.get("content_features", []),
}
CONTENT_FEATURES_TAGS = set(ONT.get("content_features", []))
SUBJECTS_TAGS = set(ONT.get("subjects", []))

# Translations for display layer (internal storage stays English)
TRANSLATIONS: Dict[str, Dict[str, str]] = {}
for lang_file in (ROOT / "config" / "ontology_v3").glob("translations_*.json"):
    lang = lang_file.stem.replace("translations_", "")
    try:
        TRANSLATIONS[lang] = json.load(open(lang_file))["tags"]
    except Exception as e:
        log.warning(f"Failed to load {lang_file}: {e}")
log.info(f"Translations loaded for languages: {list(TRANSLATIONS.keys())}")


def translate_tag(tag: str, lang: str) -> str:
    if not lang or lang == "en" or lang not in TRANSLATIONS:
        return tag
    return TRANSLATIONS[lang].get(tag, tag)

# ─── FastAPI ──────────────────────────────────────────────────────────────
app = FastAPI(title="MindRead V3 API",
              description="Emotionsbasierte Filmsuche — Sparse+Dense Hybrid",
              version="3.0.0",
              docs_url="/api/docs")

app.add_middleware(CORSMiddleware,
                    allow_origins=["*"], allow_credentials=True,
                    allow_methods=["*"], allow_headers=["*"])


# ─── Models ──────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    similar_to: Optional[int] = Field(None, description="tmdb_id des Referenz-Films")
    query: Optional[str] = Field(None, description="Freitext-Query")
    limit: int = Field(10, ge=1, le=50)

    w_synopsis: float = Field(0.35, ge=0.0, le=1.0)
    w_emotion: float = Field(0.35, ge=0.0, le=1.0)
    w_theme: float = Field(0.30, ge=0.0, le=1.0)
    indie_mainstream: float = Field(0.0, ge=-1.0, le=1.0,
                                    description="-1=indie, 0=neutral, +1=mainstream")

    year_min: Optional[int] = None
    year_max: Optional[int] = None
    runtime_min: Optional[int] = Field(60, description="Default 60 → keine Featurettes")
    runtime_max: Optional[int] = None
    min_vote_count: int = 0
    genre: List[str] = Field(default_factory=list)
    gender: Optional[str] = Field(None, pattern="^(male|female|ensemble|non_binary)$")

    # Avoid lists (manuell oder vom LLM aus Free-Text)
    avoid_emotions: List[str] = Field(default_factory=list)
    avoid_themes: List[str] = Field(default_factory=list)
    avoid_content: List[str] = Field(default_factory=list,
        description="Content features to avoid (firearms, graphic_violence, sexual_content, ...). "
                    "Applied as a hard Qdrant filter against payload.content_features.<tag>. "
                    "Films extracted before this field existed have content_features=None and pass through gracefully.")
    avoid_strict: bool = Field(False, description="True = harte Filter, False = Score-Penalty")

    # Streaming-Provider filter (multi-select). Empty = all providers ok.
    # Tenant whitelist (env TENANT_PROVIDERS_ALLOWED) further restricts what's accepted.
    streaming_providers: List[str] = Field(default_factory=list)

    # Display language: returns title_<lang> / overview_<lang> if available, translates tags
    lang: str = Field("en", pattern="^(en|de)$",
        description="Display language. Internal processing stays English regardless.")

    # Adjusted intent (used by Wheel after LLM extracted, user nudged tags)
    # If set, BACKEND SKIPS LLM and uses these directly.
    adjusted_emotions: Optional[Dict[str, float]] = None
    adjusted_themes: Optional[Dict[str, float]] = None

    # ── User profile / collaborative-filter signal ──────────────────────
    # Variant A (simple): provider sends liked film IDs, we build DNA mean.
    # Privacy: nothing stored server-side, sent per request.
    liked_tmdb_ids: List[int] = Field(default_factory=list,
        description="Up to ~50 IDs of films the user liked. Used as collaborative signal.")
    w_personal: float = Field(0.0, ge=0.0, le=1.0,
        description="Weight of the user-profile channel (0=ignore, 1=heavy bias toward user history)")

    # Variant B (advanced): provider's own ML pre-computes scores per film,
    # we apply them as a multiplicative re-rank boost. Decouples our retrieval
    # from any specific recommender model — perfect for B2B integration.
    external_score_boost: Dict[int, float] = Field(default_factory=dict,
        description="{tmdb_id: score [0..1]}. Provider's ML output. Boost final score = score × (1 + w_external × external).")
    w_external: float = Field(0.0, ge=0.0, le=2.0,
        description="Weight of external ML scores. 0=ignore, 1=equal weight, 2=external dominates.")

    class Config:
        json_schema_extra = {
            "examples": [
                {"similar_to": 245891, "limit": 10, "w_synopsis": 0.5,
                 "w_emotion": 0.3, "w_theme": 0.2},
                {"query": "düstere Rachefilme mit Happy End", "limit": 10,
                 "indie_mainstream": -0.5},
            ]
        }


class MatchReason(BaseModel):
    tag: str
    query_weight: float
    film_weight: float
    contribution: float    # query_w × film_w


class FilmResult(BaseModel):
    tmdb_id: int
    title: str
    year: Optional[int]
    overview: str
    score: float
    channels: Dict[str, float]
    genres: List[str]
    archetype: Optional[str]
    protagonist_gender: Optional[str]
    runtime: Optional[int]
    vote_count: Optional[int]
    vote_average: Optional[float]
    popularity: Optional[float] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    emotion_dna: Dict[str, float]
    theme_dna: Dict[str, float]
    setting: Dict[str, float]
    mood: Dict[str, float]
    pacing: Dict[str, float]
    streaming_providers: List[str] = Field(default_factory=list)
    # Why was this film matched (top tags shared with query)
    match_emotions: List[MatchReason] = Field(default_factory=list)
    match_themes: List[MatchReason] = Field(default_factory=list)


class IntentInfo(BaseModel):
    """Was das LLM aus der Free-Text-Query rausextrahiert hat."""
    emotion_sparse: Dict[str, float]
    theme_sparse: Dict[str, float]
    avoid_emotions: List[str]
    avoid_themes: List[str]
    avoid_content: List[str] = Field(default_factory=list)
    similar_to_title: Optional[str]
    protagonist_gender: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None


class SearchResponse(BaseModel):
    query: Optional[str]
    similar_to: Optional[int]
    reference_title: Optional[str]
    intent: Optional[IntentInfo]
    weights_used: Dict[str, float]
    results: List[FilmResult]
    search_time_ms: int


# ─── LLM helper for free-text ─────────────────────────────────────────────
def llm_query_to_dna(query: str) -> Dict[str, Any]:
    """Run LLM (OpenAI or local Qwen) on the free-text query, extract DNA-like dict.
    Provider chosen via LOCAL_LLM_ENABLED env var."""
    if LOCAL_LLM_ENABLED:
        from scripts.llm_local import llm_query_to_dna_local
        return llm_query_to_dna_local(query, SYSTEM_PROMPT, ONT)
    # Fallthrough: OpenAI
    is_new = ("gpt-5" in OPENAI_MODEL) or OPENAI_MODEL.startswith(("o3", "o4", "o1"))
    user = f"""The user query (search request, not film description):
"{query}"

Extract the same DNA schema as if this were a film description, representing what the
user WANTS to see/feel. 2-5 tags per block, weights reflect priority. If the user says
"without X" or "ohne X", do NOT include those tags but list them in
"avoid_emotions" and "avoid_themes" arrays. Return strict JSON.

For ambiguous genre/style words, map aggressively to canonical tags:
  - "cyberpunk" → Action, Science Fiction, identity_crisis, dystopian themes
  - "noir"      → noir mood, mystery_investigation, dark atmosphere
  - "feel-good" → comforting, inspiring, joy, light mood
  - "tearjerker"→ grief, bittersweet, sadness

For subject queries, fill the "subjects" block with the matching canonical tag(s) from
the SUBJECTS bucket above. This is the strongest signal for "give me films ABOUT X":
  - "Mafiafilme" / "Gangsterfilme" → subjects={{"mafia": 1.0}}
  - "Vampirfilme" → subjects={{"vampire": 1.0}}
  - "Spionagefilme" → subjects={{"espionage": 1.0}}
  - "Kampfsportfilme" → subjects={{"martial_arts": 1.0}}
  - "Sportfilme" → subjects={{"sports": 1.0}}
  - "Knastfilme" / "prison" → subjects={{"prison_life": 1.0}}
  - "Anime" → subjects={{"anime": 1.0}}
  - "Found-Footage Horror" → subjects={{"found_footage": 0.6}}, themes={{"Horror": 0.4}}
  - "Biopic über Musiker" → subjects={{"biopic": 0.6, "music_performance": 0.4}}

CRITICAL — "wie X aber Y" / "like X but Y" handling:
  When the user references a film AND a transformation ("aber X", "but with X",
  "nur X", "more X", "less X"), the emotions/themes you output must reflect ONLY
  the SHIFT/MODIFIER, NOT the reference film's DNA. The reference film's full DNA
  will be loaded separately from `similar_to_title`. Your job is to encode the DELTA.

  Examples:
   - "Filme wie Amélie aber mit mehr Action" → similar_to_title="Amélie",
     emotions={{excitement: 0.5, anticipation: 0.5}}, themes={{Action: 0.7, Adventure: 0.3}}
     (do NOT include joy/wonder/Amélie tags — they come from the reference)
   - "John Wick aber lustiger" → similar_to_title="John Wick",
     emotions={{joy: 0.5, amusement: 0.5}}, themes={{Comedy: 1.0}}
   - "Inception aber emotional" → similar_to_title="Inception",
     emotions={{grief: 0.4, tenderness: 0.4, melancholy: 0.2}}, themes={{}}

Additional fields:
  "translated_query": "<English translation of the user's query>"
                      ALWAYS provide a fluent English translation. If the user wrote
                      English, copy it verbatim. This is used for semantic search.
  "avoid_emotions": [tag, ...]
  "avoid_themes":   [tag, ...]
  "avoid_content":  [tag, ...]   // content features to avoid: firearms, bladed_weapons,
                                 // physical_combat, explosions, supernatural_combat,
                                 // vehicular_combat, graphic_violence, torture,
                                 // sexual_content, drug_use.
                                 // Trigger phrases:
                                 //  - "ohne Schusswaffen" / "no guns" → ["firearms"]
                                 //  - "ohne Waffen" / "no weapons" → ["firearms","bladed_weapons"]
                                 //  - "kein Kampf" / "no fighting" → ["firearms","bladed_weapons","physical_combat"]
                                 //  - "ohne Gewalt" / "no violence" → ["graphic_violence","torture"]
                                 //  - "kindgeeignet" / "for kids" → ["graphic_violence","torture","sexual_content","drug_use"]
                                 // Use [] (empty) if no avoidance phrase. Only canonical tags.
  "similar_to_title": null | "Film Title in ENGLISH original"  (if user says "wie X" / "like X")
                     ALWAYS use the English/original-language title, never the German one.
                     Examples: "Im Auftrag des Teufels" → "The Devil's Advocate"
                              "Der Pate" → "The Godfather"
                              "Stirb langsam" → "Die Hard"
  "protagonist_gender": null | "male" | "female" | "ensemble" | "non_binary"
                       Set when the user explicitly demands a protagonist gender:
                        - "weibliche Hauptrolle", "starke Frau", "female lead" → "female"
                        - "männlicher Held", "male lead" → "male"
                        - "Ensemble-Cast", "Gruppe" → "ensemble"
                       Otherwise null. Do NOT infer from genre alone.
  "year_min": null | number   (4-digit year, inclusive)
  "year_max": null | number   (4-digit year, inclusive)
                  Set when the user mentions an era/decade. Examples:
                   - "80er Filme" / "1980s" → year_min=1980, year_max=1989
                   - "90er Liebeskomödie" → year_min=1990, year_max=1999
                   - "neue Filme" / "recent" → year_min=2020 (no max)
                   - "Klassiker" / "classics" → year_max=1980 (no min)
                  Otherwise null/null.
"""
    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user}],
        ("max_completion_tokens" if is_new else "max_tokens"): 1500,
        "response_format": {"type": "json_object"},
    }
    if not is_new:
        body["temperature"] = 0.1
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                               "Content-Type": "application/json"},
                      json=body, timeout=60)
    if r.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"LLM call failed: {r.status_code} {r.text[:200]}")
    raw = json.loads(r.json()["choices"][0]["message"]["content"])
    dna = normalize_dna(raw, ONT)
    dna["avoid_emotions"] = [t for t in (raw.get("avoid_emotions") or []) if isinstance(t, str)]
    dna["avoid_themes"] = [t for t in (raw.get("avoid_themes") or []) if isinstance(t, str)]
    dna["avoid_content"] = [t for t in (raw.get("avoid_content") or [])
                             if isinstance(t, str) and t in CONTENT_FEATURES_TAGS]
    dna["similar_to_title"] = raw.get("similar_to_title")
    dna["translated_query"] = raw.get("translated_query") or query  # fallback to original
    pg = (raw.get("protagonist_gender") or "").lower() or None
    dna["protagonist_gender"] = pg if pg in {"male", "female", "ensemble", "non_binary"} else None
    ymin, ymax = raw.get("year_min"), raw.get("year_max")
    dna["year_min"] = int(ymin) if isinstance(ymin, (int, float)) and 1900 <= int(ymin) <= 2100 else None
    dna["year_max"] = int(ymax) if isinstance(ymax, (int, float)) and 1900 <= int(ymax) <= 2100 else None
    return dna


# ─── Endpoints ────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    try:
        info = QDRANT.get_collection(COLLECTION)
        # Count rows in the extracted JSONL — cheap line-count, gives the user
        # visible "extraction progress" vs what's currently indexed in Qdrant.
        extracted = 0
        jsonl = ROOT / "data" / "movies_dna_v3.jsonl"
        if jsonl.exists():
            with open(jsonl, "rb") as f:
                extracted = sum(1 for _ in f)
        indexed = info.points_count or 0
        return {
            "status": "healthy",
            "collection": COLLECTION,
            "points": indexed,
            "indexed_vectors": info.indexed_vectors_count,
            "extracted_total": extracted,
            "pending_reindex": max(0, extracted - indexed),
            "ontology_buckets": {k: len(v) for k, v in ONTOLOGY_BUCKETS.items()},
            "llm": "local-qwen" if LOCAL_LLM_ENABLED else OPENAI_MODEL,
            "tenant_providers_allowed": TENANT_PROVIDERS_ALLOWED or "all",
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/api/providers")
def get_providers():
    """List streaming providers seen in the current collection (for UI checkboxes)."""
    # Sample top providers via scroll
    counter: Dict[str, int] = {}
    offset = None
    scanned = 0
    while True:
        pts, offset = QDRANT.scroll(COLLECTION, limit=1000, offset=offset,
                                     with_payload=["streaming_providers"], with_vectors=False)
        if not pts: break
        for p in pts:
            for prov in (p.payload.get("streaming_providers") or []):
                counter[prov] = counter.get(prov, 0) + 1
            scanned += 1
        if offset is None: break
    # Sort + apply tenant whitelist
    items = sorted(counter.items(), key=lambda x: -x[1])
    if TENANT_PROVIDERS_ALLOWED:
        items = [(p, c) for p, c in items if p in TENANT_PROVIDERS_ALLOWED]
    return {
        "scanned": scanned,
        "tenant_whitelist": TENANT_PROVIDERS_ALLOWED or None,
        "providers": [{"name": p, "film_count": c} for p, c in items],
    }


@app.get("/api/ontology")
def get_ontology(lang: str = "en"):
    """Tag-Listen pro Bucket — füttert das Wheel-UI. lang=de für deutsche Labels."""
    return {
        "buckets": ONTOLOGY_BUCKETS,
        "definitions": ONT["definitions"],
        "synonyms": ONT["synonyms"],
        "labels": TRANSLATIONS.get(lang) if lang in TRANSLATIONS else None,
        "available_languages": ["en"] + sorted(TRANSLATIONS.keys()),
    }


@app.get("/api/film/{tmdb_id}")
def get_film(tmdb_id: int):
    pts = QDRANT.retrieve(COLLECTION, ids=[tmdb_id], with_payload=True)
    if not pts:
        raise HTTPException(404, f"Film {tmdb_id} not in collection")
    return pts[0].payload


def _build_title_index():
    """One-time at startup: scroll all titles into an in-memory dict.
    Avoids per-query Qdrant scrolls for similar_to_title lookup."""
    log.info("Building title index from Qdrant…")
    offset = None
    n = 0
    while True:
        pts, offset = QDRANT.scroll(COLLECTION, limit=1000, offset=offset,
                                     with_payload=["tmdb_id", "title", "original_title"],
                                     with_vectors=False)
        if not pts:
            break
        for p in pts:
            pl = p.payload or {}
            tid = pl.get("tmdb_id") or p.id
            for key in ("title", "original_title"):
                t = pl.get(key)
                if t:
                    TITLE_INDEX[t.lower()] = tid
            TITLE_PAYLOADS[tid] = {"title": pl.get("title"), "original_title": pl.get("original_title")}
            n += 1
        if offset is None:
            break
    log.info(f"Title index: {len(TITLE_INDEX)} title-keys for {n} films")


def _find_film_by_title(title: str):
    """Fast in-memory lookup: exact, then substring against the title index."""
    if not title:
        return None
    target = title.strip().lower()
    # Exact
    if target in TITLE_INDEX:
        tid = TITLE_INDEX[target]
        pts = QDRANT.retrieve(COLLECTION, ids=[tid], with_payload=True)
        return pts[0] if pts else None
    # Substring (in-memory)
    matches = [(t, tid) for t, tid in TITLE_INDEX.items()
                if target in t or t in target]
    if not matches:
        return None
    # Prefer shortest matching title (more likely to be the actual film, not a sequel)
    matches.sort(key=lambda x: abs(len(x[0]) - len(target)))
    tid = matches[0][1]
    pts = QDRANT.retrieve(COLLECTION, ids=[tid], with_payload=True)
    return pts[0] if pts else None


# Pre-load E5 model + title index at startup so first query isn't slow
try:
    log.info("Pre-loading E5 model (one-time, ~10-20s)…")
    encode_query_text("warmup")
    log.info("E5 ready.")
except Exception as e:
    log.warning(f"E5 preload failed: {e}")
_build_title_index()


def _compute_matches(query_dna: Dict[str, float],
                     film_dna: Dict[str, float],
                     top_n: int = 3) -> List[MatchReason]:
    if not query_dna or not film_dna:
        return []
    out = []
    for tag, qw in query_dna.items():
        fw = film_dna.get(tag, 0.0)
        if fw > 0:
            out.append(MatchReason(tag=tag, query_weight=float(qw),
                                   film_weight=float(fw), contribution=float(qw * fw)))
    out.sort(key=lambda x: -x.contribution)
    return out[:top_n]


def _to_film_result(item: Dict[str, Any],
                    query_emo: Optional[Dict[str, float]] = None,
                    query_th: Optional[Dict[str, float]] = None,
                    lang: str = "en") -> FilmResult:
    p = item["payload"]
    film_emo = p.get("emotion_dna") or {}
    film_th = p.get("theme_dna") or {}
    # Pick display fields by language with English fallback
    title = p.get(f"title_{lang}") if lang != "en" else None
    title = title or p.get("title") or "?"
    overview = p.get(f"overview_{lang}") if lang != "en" else None
    overview = overview or p.get("overview") or ""
    return FilmResult(
        tmdb_id=p.get("tmdb_id"),
        title=title,
        year=p.get("year"),
        overview=overview[:500],
        score=float(item["score"]),
        channels={k: float(v) for k, v in (item.get("channels") or {}).items()},
        genres=p.get("genres") or [],
        archetype=p.get("archetype"),
        protagonist_gender=p.get("protagonist_gender"),
        runtime=p.get("runtime"),
        vote_count=p.get("vote_count"),
        vote_average=p.get("vote_average"),
        popularity=p.get("popularity"),
        poster_path=p.get("poster_path"),
        backdrop_path=p.get("backdrop_path"),
        emotion_dna=film_emo,
        theme_dna=film_th,
        setting=p.get("setting") or {},
        mood=p.get("mood") or {},
        pacing=p.get("pacing") or {},
        streaming_providers=p.get("streaming_providers") or [],
        match_emotions=_compute_matches(query_emo or {}, film_emo) if query_emo else [],
        match_themes=_compute_matches(query_th or {}, film_th) if query_th else [],
    )


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    if req.similar_to is None and not req.query:
        raise HTTPException(400, "Either `similar_to` or `query` is required.")

    t0 = time.time()
    weights = {"w_synopsis": req.w_synopsis,
               "w_emotion": req.w_emotion,
               "w_theme": req.w_theme}
    # Apply tenant provider whitelist if configured
    requested_providers = req.streaming_providers or []
    if TENANT_PROVIDERS_ALLOWED:
        if requested_providers:
            requested_providers = [p for p in requested_providers if p in TENANT_PROVIDERS_ALLOWED]
            if not requested_providers:
                raise HTTPException(400, f"None of requested providers are allowed for this tenant. "
                                          f"Allowed: {TENANT_PROVIDERS_ALLOWED}")
        else:
            # No explicit filter from user — apply tenant default: only show their providers
            requested_providers = list(TENANT_PROVIDERS_ALLOWED)

    must = []
    if req.genre:
        for g in req.genre:
            must.append(FieldCondition(key="genres", match=MatchValue(value=g)))
    if req.year_min is not None:
        must.append(FieldCondition(key="year", range=Range(gte=req.year_min)))
    if req.year_max is not None:
        must.append(FieldCondition(key="year", range=Range(lte=req.year_max)))
    if req.runtime_min is not None:
        must.append(FieldCondition(key="runtime", range=Range(gte=req.runtime_min)))
    if req.runtime_max is not None:
        must.append(FieldCondition(key="runtime", range=Range(lte=req.runtime_max)))
    if req.min_vote_count:
        must.append(FieldCondition(key="vote_count", range=Range(gte=req.min_vote_count)))
    if req.gender:
        must.append(FieldCondition(key="protagonist_gender", match=MatchValue(value=req.gender)))
    if requested_providers:
        # Match if film has at least one of the requested providers
        must.append(FieldCondition(key="streaming_providers", match=MatchAny(any=requested_providers)))
    filt = Filter(must=must) if must else None

    synopsis_vec = None
    emotion_sparse = None
    theme_sparse = None
    intent: Optional[IntentInfo] = None
    reference_title: Optional[str] = None
    query_emo: Dict[str, float] = {}
    query_th: Dict[str, float] = {}

    if req.similar_to:
        ref = QDRANT.retrieve(COLLECTION, ids=[req.similar_to],
                              with_payload=True, with_vectors=True)
        if not ref:
            raise HTTPException(404, f"similar_to={req.similar_to} not in collection")
        rp = ref[0]
        reference_title = (rp.payload or {}).get("title")
        query_emo = (rp.payload or {}).get("emotion_dna") or {}
        query_th = (rp.payload or {}).get("theme_dna") or {}
        vec = rp.vector or {}
        synopsis_vec = np.array(vec.get("synopsis_dense")) if vec.get("synopsis_dense") is not None else None
        es = vec.get("emotion_sparse"); ts = vec.get("theme_sparse")
        from qdrant_client.models import SparseVector
        emotion_sparse = SparseVector(indices=list(es.indices), values=list(es.values)) if es else None
        theme_sparse = SparseVector(indices=list(ts.indices), values=list(ts.values)) if ts else None
    elif req.adjusted_emotions or req.adjusted_themes:
        # Wheel-only adjustment, no LLM call
        query_emo = req.adjusted_emotions or {}
        query_th = req.adjusted_themes or {}
        synopsis_vec = encode_query_text(req.query) if req.query else None
        emotion_sparse = to_sparse(query_emo, EMOTION_IDX)
        # Note: adjusted_themes covers all 88 dims (themes/genres/settings/moods/pacing)
        theme_sparse = to_sparse(query_th, THEME_IDX)
    else:
        # Free-text via LLM
        dna = llm_query_to_dna(req.query)
        query_emo = dna.get("emotion_sparse", {})
        # Combine themes+genres with settings/moods/pacing/subjects for the wider sparse layout
        query_th = {
            **(dna.get("theme_sparse") or {}),
            **(dna.get("setting") or {}),
            **(dna.get("mood") or {}),
            **(dna.get("pacing") or {}),
            **(dna.get("subjects") or {}),
        }

        # If LLM detected "wie X" reference, try to resolve title → DNA
        ref_title = dna.get("similar_to_title")
        ref_dna_used = False
        if ref_title:
            ref_film = _find_film_by_title(ref_title)
            if ref_film:
                ref_payload = ref_film.payload or {}
                reference_title = ref_payload.get("title")
                # Blend: 60% reference film DNA + 40% LLM-extracted modifier
                ref_emo = ref_payload.get("emotion_dna", {})
                ref_th  = ref_payload.get("theme_dna", {})
                if ref_emo:
                    blended_emo = {}
                    for t, w in ref_emo.items():
                        blended_emo[t] = blended_emo.get(t, 0) + w * 0.6
                    for t, w in query_emo.items():
                        blended_emo[t] = blended_emo.get(t, 0) + w * 0.4
                    # Re-normalize to L1=1 — guards against drift when the modifier
                    # is empty (pure "wie X" returns 0.6·ref otherwise). Audit F-015.
                    query_emo = normalize_l1(blended_emo)
                if ref_th:
                    blended_th = {}
                    for t, w in ref_th.items():
                        blended_th[t] = blended_th.get(t, 0) + w * 0.6
                    for t, w in query_th.items():
                        blended_th[t] = blended_th.get(t, 0) + w * 0.4
                    query_th = normalize_l1(blended_th)
                # Also use reference film's synopsis_dense as base, blend later
                ref_dna_used = True
                log.info(f"Resolved similar_to_title='{ref_title}' → {reference_title} (blended)")

        intent = IntentInfo(
            emotion_sparse=query_emo,
            theme_sparse=query_th,
            avoid_emotions=dna.get("avoid_emotions") or [],
            avoid_themes=dna.get("avoid_themes") or [],
            avoid_content=dna.get("avoid_content") or [],
            similar_to_title=ref_title,
            protagonist_gender=dna.get("protagonist_gender"),
            year_min=dna.get("year_min"),
            year_max=dna.get("year_max"),
        )

        # Promote LLM-derived hard filters into the Qdrant `must` list, but only if
        # the request didn't already specify them (caller wins). Adding them after
        # the original must-list was built means the next `manual_weighted_fusion`
        # call sees the augmented filter.
        extra_must = []
        if dna.get("protagonist_gender") and not req.gender:
            extra_must.append(FieldCondition(
                key="protagonist_gender",
                match=MatchValue(value=dna["protagonist_gender"]),
            ))
        if dna.get("year_min") is not None and req.year_min is None:
            extra_must.append(FieldCondition(
                key="year", range=Range(gte=dna["year_min"]),
            ))
        if dna.get("year_max") is not None and req.year_max is None:
            extra_must.append(FieldCondition(
                key="year", range=Range(lte=dna["year_max"]),
            ))
        if extra_must:
            must.extend(extra_must)
            filt = Filter(must=must)
            log.info(f"LLM-derived filters added: gender={dna.get('protagonist_gender')} "
                     f"year=[{dna.get('year_min')},{dna.get('year_max')}]")
        # synopsis_vec: if reference resolved, use its stored vector; else encode TRANSLATED query text
        if ref_dna_used and ref_film:
            ref_pts = QDRANT.retrieve(COLLECTION, ids=[ref_film.id], with_vectors=True)
            if ref_pts and ref_pts[0].vector:
                synopsis_vec = np.array(ref_pts[0].vector.get("synopsis_dense"))
        if synopsis_vec is None:
            translated = dna.get("translated_query") or req.query
            log.info(f"Encoding query: original={req.query!r}  translated={translated!r}")
            synopsis_vec = encode_query_text(translated)
        emotion_sparse = to_sparse(query_emo, EMOTION_IDX)
        theme_sparse = to_sparse(query_th, THEME_IDX)

    # Combine user-supplied avoids with LLM-extracted ones (free-text path)
    avoid_emotions = list(set((req.avoid_emotions or []) +
                                  (intent.avoid_emotions if intent else [])))
    avoid_themes = list(set((req.avoid_themes or []) +
                                (intent.avoid_themes if intent else [])))
    avoid_content = list(set((req.avoid_content or []) +
                                 (intent.avoid_content if intent else [])))
    # Filter to canonical tags only
    avoid_emotions = [t for t in avoid_emotions if t in EMOTION_IDX]
    avoid_themes = [t for t in avoid_themes if t in THEME_IDX]
    avoid_content = [t for t in avoid_content if t in CONTENT_FEATURES_TAGS]

    # avoid_content → Qdrant `must_not` filter on payload.content_features.<tag> > 0.
    # Films extracted before content_features existed have the field absent → must_not
    # is graceful (a film without the key cannot match the inner condition).
    if avoid_content:
        must_not = [FieldCondition(key=f"content_features.{tag}", range=Range(gt=0))
                    for tag in avoid_content]
        # rebuild filt — preserve existing must conditions
        filt = Filter(must=must, must_not=must_not) if (must or must_not) else None
        log.info(f"avoid_content filter active: {avoid_content}")

    # ── Build user-profile channel from liked films ─────────────────────
    user_emotion_sparse = None
    user_theme_sparse = None
    user_synopsis_vec = None
    user_profile_meta = None
    if req.liked_tmdb_ids and req.w_personal > 0:
        liked = req.liked_tmdb_ids[:50]   # cap
        user_pts = QDRANT.retrieve(COLLECTION, ids=liked,
                                    with_payload=True, with_vectors=True)
        if user_pts:
            # Average emotion_dna and theme_dna across liked films
            from qdrant_client.models import SparseVector as _SV
            sum_emo: Dict[str, float] = {}
            sum_th: Dict[str, float] = {}
            sum_syn = None
            n = 0
            for p in user_pts:
                pl = p.payload or {}
                vec = p.vector or {}
                for t, w in (pl.get("emotion_dna") or {}).items():
                    sum_emo[t] = sum_emo.get(t, 0.0) + float(w)
                for t, w in (pl.get("theme_dna") or {}).items():
                    sum_th[t] = sum_th.get(t, 0.0) + float(w)
                sd = vec.get("synopsis_dense")
                if sd is not None:
                    arr = np.array(sd)
                    sum_syn = arr if sum_syn is None else sum_syn + arr
                n += 1
            if n > 0:
                avg_emo = {k: v/n for k, v in sum_emo.items()}
                avg_th = {k: v/n for k, v in sum_th.items()}
                user_emotion_sparse = to_sparse(avg_emo, EMOTION_IDX)
                user_theme_sparse = to_sparse(avg_th, THEME_IDX)
                if sum_syn is not None:
                    avg_syn = sum_syn / n
                    norm = np.linalg.norm(avg_syn)
                    if norm > 1e-6:
                        user_synopsis_vec = avg_syn / norm
                user_profile_meta = {
                    "liked_count": n,
                    "top_emotions": sorted(avg_emo.items(), key=lambda x: -x[1])[:5],
                    "top_themes": sorted(avg_th.items(), key=lambda x: -x[1])[:5],
                }

    raw = manual_weighted_fusion(
        QDRANT, synopsis_vec, emotion_sparse, theme_sparse,
        weights, filt, req.limit + (1 if req.similar_to else 0),
        popularity_boost=req.indie_mainstream,
        avoid_emotions=avoid_emotions,
        avoid_themes=avoid_themes,
        avoid_strict=req.avoid_strict,
        diversify_results=True,
        similar_to_id=req.similar_to,
        user_synopsis_vec=user_synopsis_vec,
        user_emotion_sparse=user_emotion_sparse,
        user_theme_sparse=user_theme_sparse,
        w_personal=req.w_personal if user_profile_meta else 0.0,
    )
    if req.similar_to:
        raw = [r for r in raw if r["id"] != req.similar_to]

    # ── External ML boost (Variant B) ─────────────────────────────────────
    if req.external_score_boost and req.w_external > 0:
        for r in raw:
            ext = req.external_score_boost.get(r["id"]) or req.external_score_boost.get(str(r["id"]))
            if ext is not None:
                ext = max(0.0, min(1.0, float(ext)))
                r["external_score"] = ext
                r["score"] = r["score"] * (1.0 + req.w_external * ext)
        raw = sorted(raw, key=lambda x: -x["score"])

    results = [_to_film_result(r, query_emo, query_th, lang=req.lang) for r in raw[: req.limit]]
    # Translate match-reason tags for display
    if req.lang != "en" and req.lang in TRANSLATIONS:
        for fr in results:
            for m in fr.match_emotions: m.tag = translate_tag(m.tag, req.lang)
            for m in fr.match_themes:   m.tag = translate_tag(m.tag, req.lang)

    return SearchResponse(
        query=req.query,
        similar_to=req.similar_to,
        reference_title=reference_title,
        intent=intent,
        weights_used=weights,
        results=results,
        search_time_ms=int((time.time() - t0) * 1000),
    )


# ─── Frontend (single-page wheel UI) ───────────────────────────────────────
FRONTEND = ROOT / "frontend"
if FRONTEND.exists():
    @app.get("/")
    def root():
        return FileResponse(FRONTEND / "index.html")
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
else:
    @app.get("/")
    def root():
        return {"name": "MindRead V3", "docs": "/api/docs",
                "note": "frontend/ directory not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
