"""
Search V3 — query the mindread_v3 collection with hybrid dense+sparse fusion.

Two query modes:
1. similar_to <tmdb_id>  → use stored vectors of that film
2. free_text "..."       → call LLM to extract DNA, build query vectors

Sliders (CLI flags):
  --w_synopsis 0.5
  --w_emotion  0.3
  --w_theme    0.2
  --indie_mainstream 0.0  (-1.0 = full indie boost, +1.0 = full mainstream boost)
  --year_min YEAR --year_max YEAR
  --runtime_min MIN --runtime_max MIN
  --genre Action --genre Thriller   (hard filter)
  --avoid_emotion despair            (soft penalty)
  --gender male                      (hard filter)

Usage:
  venv/bin/python3 scripts/search_v3.py --similar_to 245891 --w_emotion 0.4
  venv/bin/python3 scripts/search_v3.py --query "düstere Rachefilme mit Happy End"
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue, MatchAny, Range,
    NamedVector, SparseVector, ScoredPoint,
)
QDRANT_URL = f"http://{os.getenv('QDRANT_HOST', 'localhost')}:{os.getenv('QDRANT_PORT', '6333')}"

ROOT = Path(__file__).resolve().parent.parent
ONT_DIR = ROOT / "config" / "ontology_v3"
COLLECTION = os.getenv("QDRANT_COLLECTION_V3", "mindread_v3")


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_indices() -> Tuple[Dict[str, int], Dict[str, int]]:
    """Same layout as reindex_v3.load_ontology_indices() — must stay in sync.

    Theme-sparse layout (extended 2026-05): plot_themes(35) + genres(18) + settings(15) +
    moods(12) + pacing(8) + subjects(N). Subjects are APPENDED AT END so adding them
    does not shift any existing index. Films stored before subjects existed have no
    entries at indices >=88 — graceful no-op for them.
    """
    emo = json.load(open(ONT_DIR / "emotions.json"))["tags"]
    wir = json.load(open(ONT_DIR / "wirkung.json"))["tags"]
    th = json.load(open(ONT_DIR / "plot_themes.json"))["tags"]
    gn = json.load(open(ONT_DIR / "genres.json"))["tags"]
    settings = json.load(open(ONT_DIR / "settings.json"))["tags"]
    moods = json.load(open(ONT_DIR / "moods.json"))["tags"]
    pacing = json.load(open(ONT_DIR / "pacing.json"))["tags"]
    subjects_path = ONT_DIR / "subjects.json"
    subjects = json.load(open(subjects_path))["tags"] if subjects_path.exists() else []
    return ({t: i for i, t in enumerate(emo + wir)},
            {t: i for i, t in enumerate(th + gn + settings + moods + pacing + subjects)})


def to_sparse(weights: Dict[str, float], tag_to_idx: Dict[str, int]) -> SparseVector:
    indices: List[int] = []
    values: List[float] = []
    for tag, w in weights.items():
        if tag in tag_to_idx and w > 0:
            indices.append(tag_to_idx[tag])
            values.append(float(w))
    return SparseVector(indices=indices, values=values)


# Free-text → DNA via LLM (uses same prompt as DNA extractor, slightly adapted for queries)
def llm_query_to_dna(query: str) -> Dict[str, Any]:
    """Extract DNA-like dict from free-text query. Returns same schema as film DNA."""
    sys.path.insert(0, str(ROOT))
    from scripts.extract_dna_v3 import build_system_prompt, load_ontology, normalize_dna, call_openai

    ont = load_ontology()
    system = build_system_prompt(ont)
    user = f"""The user query (treat as a search request, not a film description):
"{query}"

Extract the same DNA schema as if this were a movie description. The DNA represents
what the user WANTS to see/feel. Use 2-5 tags per block, distribute weights to reflect priority.
If the user says "without X" or "ohne X", DO NOT include those tags but list them in
"avoid_emotions" and "avoid_themes" arrays. Return strict JSON.

Additional fields to include:
  "avoid_emotions": [tag, ...]
  "avoid_themes":   [tag, ...]
  "similar_to_title": null | "Film Title"  (if user says "wie X" / "like X")
"""
    raw = call_openai(system, user)
    dna = normalize_dna(raw, ont)
    dna["avoid_emotions"] = [t for t in (raw.get("avoid_emotions") or []) if isinstance(t, str)]
    dna["avoid_themes"] = [t for t in (raw.get("avoid_themes") or []) if isinstance(t, str)]
    dna["similar_to_title"] = raw.get("similar_to_title")
    return dna


def build_filter(genres: Optional[List[str]],
                 year_min: Optional[int], year_max: Optional[int],
                 runtime_min: Optional[int], runtime_max: Optional[int],
                 min_vote_count: Optional[int],
                 gender: Optional[str]) -> Optional[Filter]:
    must = []
    if genres:
        for g in genres:
            must.append(FieldCondition(key="genres", match=MatchValue(value=g)))
    if year_min is not None:
        must.append(FieldCondition(key="year", range=Range(gte=year_min)))
    if year_max is not None:
        must.append(FieldCondition(key="year", range=Range(lte=year_max)))
    if runtime_min is not None:
        must.append(FieldCondition(key="runtime", range=Range(gte=runtime_min)))
    if runtime_max is not None:
        must.append(FieldCondition(key="runtime", range=Range(lte=runtime_max)))
    if min_vote_count is not None:
        must.append(FieldCondition(key="vote_count", range=Range(gte=min_vote_count)))
    if gender:
        must.append(FieldCondition(key="protagonist_gender", match=MatchValue(value=gender)))
    return Filter(must=must) if must else None


def encode_query_text(text: str) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    if not hasattr(encode_query_text, "_model"):
        encode_query_text._model = SentenceTransformer(
            os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2"),
            device="cpu")
    return encode_query_text._model.encode(
        f"query: {text}", normalize_embeddings=True, convert_to_numpy=True)


def _condition_to_dict(c: Any) -> Dict[str, Any]:
    """Serialize a single Qdrant FieldCondition into the HTTP-API dict shape."""
    d: Dict[str, Any] = {"key": c.key}
    if c.match is not None:
        # MatchValue → {"value": x}, MatchAny → {"any": [...]}
        if hasattr(c.match, "any") and c.match.any is not None:
            d["match"] = {"any": list(c.match.any)}
        elif hasattr(c.match, "value") and c.match.value is not None:
            d["match"] = {"value": c.match.value}
    if c.range is not None:
        r = {}
        if c.range.gte is not None: r["gte"] = c.range.gte
        if c.range.lte is not None: r["lte"] = c.range.lte
        if c.range.gt is not None: r["gt"] = c.range.gt
        if c.range.lt is not None: r["lt"] = c.range.lt
        d["range"] = r
    return d


def _filter_to_dict(filt: Optional[Filter]) -> Optional[Dict[str, Any]]:
    """Serialize a Qdrant Filter into the HTTP-API dict shape.

    Includes must, must_not, and should clauses. Earlier versions of this function
    only serialized `must`, silently dropping `must_not`/`should` (audit F-001).
    """
    if not filt:
        return None
    out: Dict[str, Any] = {}
    for attr in ("must", "must_not", "should"):
        conds = getattr(filt, attr, None) or []
        if conds:
            out[attr] = [_condition_to_dict(c) for c in conds]
    return out or None


def _query_one_channel(name: str, query: Any, filter_dict: Optional[Dict],
                       limit: int) -> List[Dict[str, Any]]:
    """Use Qdrant 1.10+ /points/query endpoint via HTTP (bypasses old client)."""
    body = {
        "using": name,
        "query": query,
        "limit": limit,
        "with_payload": True,
    }
    if filter_dict:
        body["filter"] = filter_dict
    r = requests.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/query",
                      json=body, timeout=30)
    r.raise_for_status()
    return r.json()["result"]["points"]


def manual_weighted_fusion(client: QdrantClient,
                           synopsis_vec: Optional[np.ndarray],
                           emotion_sparse: Optional[SparseVector],
                           theme_sparse: Optional[SparseVector],
                           weights: Dict[str, float],
                           filt: Optional[Filter],
                           limit: int = 30,
                           popularity_boost: float = 0.0,
                           rrf_k: int = 60,
                           avoid_emotions: Optional[List[str]] = None,
                           avoid_themes: Optional[List[str]] = None,
                           avoid_strict: bool = False,
                           avoid_strict_threshold: float = 0.10,
                           avoid_penalty: float = 0.5,
                           diversify_results: bool = True,
                           similar_to_id: Optional[int] = None,
                           # ── personal/collab-filter channel ──
                           user_synopsis_vec: Optional[np.ndarray] = None,
                           user_emotion_sparse: Optional[SparseVector] = None,
                           user_theme_sparse: Optional[SparseVector] = None,
                           w_personal: float = 0.0) -> List[Dict[str, Any]]:
    """Weighted Reciprocal Rank Fusion (RRF).
    Score per film = Σ_channel weight × 1/(rrf_k + rank_in_channel).
    Robust against score-scale differences between dense (cosine 0..1) and sparse (dot, unbounded).
    Bigger over-fetch = better cross-channel coverage.
    """
    merged: Dict[int, Dict[str, Any]] = {}
    over = limit * 20  # over-fetch large enough that synopsis/emotion/theme top-N overlap
    filter_dict = _filter_to_dict(filt)

    def add(channel_name: str, hits: List[Dict[str, Any]], weight: float):
        if not hits or weight <= 0:
            return
        for rank, h in enumerate(hits, start=1):
            entry = merged.setdefault(h["id"], {"id": h["id"], "payload": h.get("payload", {}),
                                                  "channels": {}, "ranks": {}, "score": 0.0})
            entry["channels"][channel_name] = h["score"]
            entry["ranks"][channel_name] = rank
            entry["score"] += weight * (1.0 / (rrf_k + rank))

    if synopsis_vec is not None and weights.get("w_synopsis", 0) > 0:
        hits = _query_one_channel("synopsis_dense", synopsis_vec.tolist(), filter_dict, over)
        add("synopsis", hits, weights["w_synopsis"])
    if emotion_sparse is not None and emotion_sparse.indices and weights.get("w_emotion", 0) > 0:
        sparse_q = {"indices": list(emotion_sparse.indices), "values": list(emotion_sparse.values)}
        hits = _query_one_channel("emotion_sparse", sparse_q, filter_dict, over)
        add("emotion", hits, weights["w_emotion"])
    if theme_sparse is not None and theme_sparse.indices and weights.get("w_theme", 0) > 0:
        sparse_q = {"indices": list(theme_sparse.indices), "values": list(theme_sparse.values)}
        hits = _query_one_channel("theme_sparse", sparse_q, filter_dict, over)
        add("theme", hits, weights["w_theme"])
    # ── Personal channel: searches via the user's averaged DNA ────────────
    if w_personal > 0:
        if user_synopsis_vec is not None:
            hits = _query_one_channel("synopsis_dense", user_synopsis_vec.tolist(),
                                        filter_dict, over)
            add("personal_syn", hits, w_personal * 0.5)
        if user_emotion_sparse is not None and user_emotion_sparse.indices:
            sq = {"indices": list(user_emotion_sparse.indices),
                  "values": list(user_emotion_sparse.values)}
            hits = _query_one_channel("emotion_sparse", sq, filter_dict, over)
            add("personal_emo", hits, w_personal * 0.25)
        if user_theme_sparse is not None and user_theme_sparse.indices:
            sq = {"indices": list(user_theme_sparse.indices),
                  "values": list(user_theme_sparse.values)}
            hits = _query_one_channel("theme_sparse", sq, filter_dict, over)
            add("personal_th", hits, w_personal * 0.25)

    # Popularity boost — scaled to RRF magnitude (~ 1/(k+rank) ≈ 0.016 for rank 1)
    if popularity_boost != 0.0 and merged:
        pops = [(e["payload"].get("vote_count") or 0) for e in merged.values()]
        log_pops = [np.log1p(p) for p in pops]
        if log_pops:
            lp_min, lp_max = min(log_pops), max(log_pops)
            denom = max(lp_max - lp_min, 1e-6)
            scale = 0.01  # similar magnitude as a top RRF contribution
            for e in merged.values():
                lp = np.log1p(e["payload"].get("vote_count") or 0)
                pop_norm = (lp - lp_min) / denom
                if popularity_boost > 0:
                    e["score"] += popularity_boost * scale * pop_norm
                else:
                    va = e["payload"].get("vote_average") or 0.0
                    if va >= 7.0:
                        e["score"] += abs(popularity_boost) * scale * (1 - pop_norm)

    # ── Avoid handling ──────────────────────────────────────────────────
    avoid_emo_set = set((avoid_emotions or []))
    avoid_th_set = set((avoid_themes or []))
    if avoid_emo_set or avoid_th_set:
        kept = {}
        for fid, e in merged.items():
            payload = e.get("payload", {}) or {}
            emo = payload.get("emotion_dna", {}) or {}
            th = payload.get("theme_dna", {}) or {}
            # Mass on avoided tags
            mass_emo = sum(w for t, w in emo.items() if t in avoid_emo_set)
            mass_th = sum(w for t, w in th.items() if t in avoid_th_set)
            total_mass = mass_emo + mass_th
            if avoid_strict and total_mass > avoid_strict_threshold:
                continue  # drop
            if total_mass > 0:
                # soft penalty proportional to mass on avoided tags
                e["score"] -= avoid_penalty * total_mass * 0.02  # similar magnitude as RRF top score
                e["avoided_mass"] = round(total_mass, 3)
            kept[fid] = e
        merged = kept

    out = sorted(merged.values(), key=lambda x: -x["score"])
    if not diversify_results:
        return out[:limit]
    return diversify(out, limit=limit, similar_to_id=similar_to_id)


def diversify(results: List[Dict[str, Any]], limit: int = 10,
              similar_to_id: Optional[int] = None,
              max_per_franchise: int = 2,        # allow up to 2 per franchise
              demotion_strength: float = 0.4) -> List[Dict[str, Any]]:
    """
    Demote sequels/franchise-mates already represented in the top-N.

    Heuristic: extract a "franchise-key" from each title (everything before ':' or
    a Roman numeral / sequel marker / volume number). After picking each result,
    boost competitors with different keys so the next top spot tends to differ.
    """
    import re
    if not results:
        return []

    def key_of(title: str) -> str:
        if not title: return ""
        t = title.strip()
        # Strip after colon "John Wick: Chapter 2" → "John Wick"
        t = t.split(":")[0]
        # Strip "Vol. N", "Part N", " 2", " II", " III" suffixes
        t = re.sub(r"\s+(vol\.?\s*\d+|part\s*\d+|chapter\s*\d+|kapitel\s*\d+|"
                   r"i{2,}|iv|v|vi{0,3}|ix|xi{0,3}|\d+)\s*$", "", t, flags=re.IGNORECASE)
        return t.strip().lower()

    # Determine reference franchise key (so we don't demote the reference's siblings as harshly)
    ref_key = None
    if similar_to_id is not None:
        for r in results:
            if r.get("id") == similar_to_id:
                ref_key = key_of((r.get("payload") or {}).get("title") or "")
                break

    chosen = []
    franchise_count: Dict[str, int] = {}
    pool = list(results)

    def _cap_for(k: str) -> int:
        # Reference franchise gets a doubled cap (user explicitly wanted "wie X" — give them sequels)
        return max_per_franchise * 2 if k == ref_key else max_per_franchise

    while pool and len(chosen) < limit:
        best_idx = -1
        best_adj_score = -1e9
        for i, r in enumerate(pool):
            title = (r.get("payload") or {}).get("title") or ""
            k = key_of(title)
            count = franchise_count.get(k, 0)
            # Skip candidates whose franchise is already capped — avoids the previous
            # bug where pop+skip silently discarded otherwise-valid items (audit F-002).
            if count >= _cap_for(k):
                continue
            # Reference franchise gets softer demotion (user wants sequels of "their" film)
            if k == ref_key:
                penalty = 0.5 * demotion_strength * count
            else:
                penalty = demotion_strength * count
            adj = r["score"] - penalty * max(r["score"], 0.001)
            if adj > best_adj_score:
                best_adj_score = adj
                best_idx = i
        if best_idx < 0:
            # No valid candidates left (all remaining are franchise-capped)
            break
        picked = pool.pop(best_idx)
        title = (picked.get("payload") or {}).get("title") or ""
        k = key_of(title)
        franchise_count[k] = franchise_count.get(k, 0) + 1
        chosen.append(picked)
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--similar_to", type=int, help="tmdb_id of reference film")
    ap.add_argument("--query", type=str, help="free-text query (uses LLM)")
    ap.add_argument("--w_synopsis", type=float, default=0.5)
    ap.add_argument("--w_emotion", type=float, default=0.3)
    ap.add_argument("--w_theme", type=float, default=0.2)
    ap.add_argument("--indie_mainstream", type=float, default=0.0,
                    help="-1=indie, 0=neutral, +1=mainstream")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--year_min", type=int)
    ap.add_argument("--year_max", type=int)
    ap.add_argument("--runtime_min", type=int, default=60, help="default 60 to skip featurettes")
    ap.add_argument("--runtime_max", type=int)
    ap.add_argument("--min_vote_count", type=int, default=0)
    ap.add_argument("--genre", action="append", help="hard genre filter (multi)")
    ap.add_argument("--gender", choices=["male", "female", "ensemble", "non_binary"])
    ap.add_argument("--fusion", choices=["rrf", "weighted"], default="weighted")
    args = ap.parse_args()

    if not args.similar_to and not args.query:
        ap.error("provide either --similar_to or --query")

    load_env()
    emotion_idx, theme_idx = load_indices()
    client = QdrantClient(host=os.getenv("QDRANT_HOST", "localhost"),
                          port=int(os.getenv("QDRANT_PORT", "6333")), timeout=30.0)

    weights = {"w_synopsis": args.w_synopsis, "w_emotion": args.w_emotion, "w_theme": args.w_theme}
    filt = build_filter(args.genre, args.year_min, args.year_max,
                        args.runtime_min, args.runtime_max,
                        args.min_vote_count or None, args.gender)

    synopsis_vec = None
    emotion_sparse = None
    theme_sparse = None
    intent_dump = None

    if args.similar_to:
        # use the stored film's vectors as query
        ref_id = args.similar_to
        ref = client.retrieve(COLLECTION, ids=[ref_id], with_payload=True, with_vectors=True)
        if not ref:
            print(f"Film {ref_id} not found in {COLLECTION}.")
            return
        ref_pt = ref[0]
        ref_vec = ref_pt.vector
        synopsis_vec = np.array(ref_vec.get("synopsis_dense"))
        es = ref_vec.get("emotion_sparse")
        ts = ref_vec.get("theme_sparse")
        emotion_sparse = SparseVector(indices=list(es.indices), values=list(es.values)) if es else None
        theme_sparse = SparseVector(indices=list(ts.indices), values=list(ts.values)) if ts else None
        print(f"\nReference: {ref_pt.payload.get('title')} ({ref_pt.payload.get('year')})  "
              f"emotion_dna={ref_pt.payload.get('emotion_dna',{})}")
        print(f"           theme_dna={ref_pt.payload.get('theme_dna',{})}\n")
    else:
        intent_dump = llm_query_to_dna(args.query)
        print(f"\nQuery: {args.query!r}")
        print(f"  intent emotion: {intent_dump.get('emotion_sparse')}")
        print(f"  intent theme:   {intent_dump.get('theme_sparse')}")
        print(f"  avoid_emotions: {intent_dump.get('avoid_emotions')}")
        print(f"  avoid_themes:   {intent_dump.get('avoid_themes')}\n")

        synopsis_vec = encode_query_text(args.query)
        emotion_sparse = to_sparse(intent_dump.get("emotion_sparse", {}), emotion_idx)
        theme_sparse = to_sparse(intent_dump.get("theme_sparse", {}), theme_idx)

    t0 = time.time()
    results = manual_weighted_fusion(client, synopsis_vec, emotion_sparse, theme_sparse,
                                     weights, filt, args.limit,
                                     popularity_boost=args.indie_mainstream)
    elapsed = (time.time() - t0) * 1000

    # filter out the reference film itself
    if args.similar_to:
        results = [r for r in results if r["id"] != args.similar_to]

    print(f"=== TOP {min(args.limit, len(results))} (search took {elapsed:.0f} ms) ===\n")
    for i, r in enumerate(results[:args.limit], 1):
        p = r["payload"]
        ch = r.get("channels", {})
        emo_top = sorted((p.get("emotion_dna") or {}).items(), key=lambda x: -x[1])[:3]
        th_top = sorted((p.get("theme_dna") or {}).items(), key=lambda x: -x[1])[:3]
        print(f"  {i:2}. {p.get('title')} ({p.get('year')}) score={r['score']:.3f}")
        print(f"      genres={p.get('genres')} archetype={p.get('archetype')} "
              f"gender={p.get('protagonist_gender')} runtime={p.get('runtime')}m votes={p.get('vote_count')}")
        print(f"      emo: {[(t, f'{v:.2f}') for t,v in emo_top]}")
        print(f"      th:  {[(t, f'{v:.2f}') for t,v in th_top]}")
        if ch:
            ch_str = ", ".join(f"{k}={v:.2f}" for k, v in ch.items())
            print(f"      channels: {ch_str}")
        print()


if __name__ == "__main__":
    main()
