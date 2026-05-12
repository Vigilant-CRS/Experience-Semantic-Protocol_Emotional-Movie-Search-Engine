"""
Re-Indexer V3 — builds new Qdrant collection mindread_v3 from
  - movies_export.json   (metadata + overview/keywords)
  - data/movies_dna_v3.jsonl (DNA from extract_dna_v3.py)

Writes:
  - mindread_v3 collection with 1 dense (synopsis) + 2 sparse (emotion, theme) named vectors
  - Payload: setting, archetype, mood, pacing, protagonist_gender + standard fields
  - Payload-Indexes on year, runtime, vote_count, vote_average, protagonist_gender, archetype

Usage:
  venv/bin/python3 scripts/reindex_v3.py --recreate
  venv/bin/python3 scripts/reindex_v3.py --limit 50           # quick test
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseVector,
    PointStruct, PayloadSchemaType, NamedVector,
)

ROOT = Path(__file__).resolve().parent.parent
ONT_DIR = ROOT / "config" / "ontology_v3"
DNA_FILE = ROOT / "data" / "movies_dna_v3.jsonl"
SOURCE = ROOT / "movies_export.json"

COLLECTION = os.getenv("QDRANT_COLLECTION_V3", "mindread_v3")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/e5-large-v2")
VECTOR_DIM = 1024


def load_ontology_indices():
    """Schema-v1 (legacy) layout. For schema-v2 use load_ontology_indices_v2().
    Stay in sync with scripts/search_v3.py:load_indices().
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
    emotion_to_idx = {t: i for i, t in enumerate(emo + wir)}                                # 30 dims
    theme_to_idx = {t: i for i, t in enumerate(th + gn + settings + moods + pacing + subjects)}
    return emotion_to_idx, theme_to_idx


def load_ontology_indices_v2():
    """Schema-v2 layout (audit F-016 + F-017 ready).
    Returns 3 maps: emotion_to_idx, theme_to_idx (no subjects), subject_to_idx.
    Stay in sync with scripts/search_v3.py:load_indices_v2().
    """
    emo = json.load(open(ONT_DIR / "emotions.json"))["tags"]
    wir = json.load(open(ONT_DIR / "wirkung.json"))["tags"]
    th = json.load(open(ONT_DIR / "plot_themes.json"))["tags"]
    gn = json.load(open(ONT_DIR / "genres.json"))["tags"]
    settings = json.load(open(ONT_DIR / "settings.json"))["tags"]
    moods = json.load(open(ONT_DIR / "moods.json"))["tags"]
    pacing = json.load(open(ONT_DIR / "pacing.json"))["tags"]
    subjects = json.load(open(ONT_DIR / "subjects.json"))["tags"]
    return (
        {t: i for i, t in enumerate(emo + wir)},                              # 30 dim
        {t: i for i, t in enumerate(th + gn + settings + moods + pacing)},    # 88 dim
        {t: i for i, t in enumerate(subjects)},                                # 24 dim
    )


def _schema_version_from_config() -> int:
    try:
        import yaml
        cfg = yaml.safe_load(open(ROOT / "config" / "engine_params.yaml")) or {}
        return int(cfg.get("schema", {}).get("version", 1))
    except Exception:
        return 1


def to_sparse(weights: Dict[str, float], tag_to_idx: Dict[str, int]) -> SparseVector:
    indices: List[int] = []
    values: List[float] = []
    for tag, w in weights.items():
        if tag in tag_to_idx and w > 0:
            indices.append(tag_to_idx[tag])
            values.append(float(w))
    return SparseVector(indices=indices, values=values)


def load_dna() -> Dict[int, Dict[str, Any]]:
    out = {}
    if not DNA_FILE.exists():
        print(f"DNA file not found: {DNA_FILE}", file=sys.stderr)
        return out
    for line in DNA_FILE.read_text().splitlines():
        try:
            rec = json.loads(line)
            out[rec["tmdb_id"]] = rec
        except Exception:
            pass
    return out


def make_synopsis_text(film: Dict[str, Any]) -> str:
    title = film.get("title") or ""
    year = film.get("year") or ""
    overview = (film.get("overview") or "").strip()
    keywords = " ".join((film.get("keywords") or [])[:15])
    return f"passage: {title} ({year}). {overview} {keywords}".strip()


def setup_collection(client: QdrantClient, recreate: bool):
    exists = client.collection_exists(COLLECTION)
    if exists and recreate:
        print(f"Deleting existing collection: {COLLECTION}")
        client.delete_collection(COLLECTION)
        exists = False
    if not exists:
        schema_v = _schema_version_from_config()
        sparse_cfg = {
            "emotion_sparse": SparseVectorParams(),
            "theme_sparse": SparseVectorParams(),
        }
        if schema_v >= 2:
            # F-017 fix: subjects get their own sparse vector
            sparse_cfg["subject_sparse"] = SparseVectorParams()
        print(f"Creating collection: {COLLECTION} (schema v{schema_v}, "
              f"sparse vectors: {list(sparse_cfg.keys())})")
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "synopsis_dense": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config=sparse_cfg,
        )
    # payload indexes
    base_indexes = [
        ("year", PayloadSchemaType.INTEGER),
        ("runtime", PayloadSchemaType.INTEGER),
        ("vote_count", PayloadSchemaType.INTEGER),
        ("vote_average", PayloadSchemaType.FLOAT),
        ("popularity", PayloadSchemaType.FLOAT),
        ("genres", PayloadSchemaType.KEYWORD),
        ("archetype", PayloadSchemaType.KEYWORD),
        ("protagonist_gender", PayloadSchemaType.KEYWORD),
        ("tmdb_id", PayloadSchemaType.INTEGER),
        # Provider-filter (audit F-003) — keyword list payload index
        ("streaming_providers", PayloadSchemaType.KEYWORD),
    ]
    # Per-tag float index on each content_features.<tag> so the avoid_content
    # must_not range-filter (gt=0) hits an index, not a linear scroll.  Audit F-004.
    content_feature_tags = []
    cf_path = ONT_DIR / "content_features.json"
    if cf_path.exists():
        content_feature_tags = json.load(open(cf_path))["tags"]
    cf_indexes = [(f"content_features.{tag}", PayloadSchemaType.FLOAT)
                  for tag in content_feature_tags]
    for field, ftype in base_indexes + cf_indexes:
        try:
            client.create_payload_index(COLLECTION, field, field_schema=ftype)
        except Exception:
            # already exists is fine
            pass
    print(f"Collection ready. Payload indexes: {len(base_indexes) + len(cf_indexes)} fields "
          f"({len(cf_indexes)} content_features keys).")


def _embedder():
    """Singleton SentenceTransformer for E5. Device picked via pick_torch_device()."""
    if not hasattr(_embedder, "_model"):
        from scripts.search_v3 import pick_torch_device
        from sentence_transformers import SentenceTransformer
        device = pick_torch_device()
        _embedder._model = SentenceTransformer(EMBEDDING_MODEL, device=device)
        _embedder._device = device
    return _embedder._model


def upsert_films(client: QdrantClient,
                 films_meta: List[Dict[str, Any]],
                 dna_records: Dict[int, Dict[str, Any]],
                 emotion_to_idx: Dict[str, int],
                 theme_to_idx: Dict[str, int],
                 subject_to_idx: Optional[Dict[str, int]] = None) -> int:
    """Build vectors + payload for the given films and upsert into Qdrant.

    Schema-aware: when subject_to_idx is provided we're in v2 mode and
    write three sparse vectors (emotion + theme + subject) plus re-normalize
    emotion_sparse with separate L1 for emotions vs wirkung (defensive: old
    JSONL entries with joint-L1 get corrected here).

    Args:
        client:        QdrantClient
        films_meta:    list of film metadata dicts (title, year, overview, …)
        dna_records:   {tmdb_id: {"dna_v3": {...}}} — extract_one() output
        emotion_to_idx, theme_to_idx: layout (from load_ontology_indices() or _v2)
        subject_to_idx: present iff schema-v2 — triggers F-017 subject_sparse build

    Returns: number of points upserted.
    """
    from scripts.extract_dna_v3 import normalize_l1 as _l1
    # Ontology buckets for defensive normalization
    ont_emo_tags = set(json.load(open(ONT_DIR / "emotions.json"))["tags"])
    ont_wir_tags = set(json.load(open(ONT_DIR / "wirkung.json"))["tags"])
    schema_v2 = subject_to_idx is not None
    model = _embedder()
    texts = [make_synopsis_text(m) for m in films_meta]
    emb = model.encode(texts, batch_size=32, convert_to_numpy=True,
                       normalize_embeddings=True, show_progress_bar=False)
    points: List[PointStruct] = []
    for i, m in enumerate(films_meta):
        tid = m["tmdb_id"]
        d = (dna_records.get(tid) or {}).get("dna_v3", {})
        payload = {
            "tmdb_id": tid,
            "title": m.get("title"),
            "original_title": m.get("original_title"),
            "year": m.get("year") or (m.get("release_date", "")[:4] or None),
            "overview": (m.get("overview") or "")[:500],
            "keywords": (m.get("keywords") or [])[:20],
            "director": m.get("director"),
            "cast": (m.get("cast") or [])[:5],
            "runtime": m.get("runtime") or 0,
            "vote_count": m.get("vote_count") or 0,
            "vote_average": float(m.get("vote_average") or 0.0),
            "popularity": float(m.get("popularity") or 0.0),
            "release_date": m.get("release_date") or "",
            "genres": m.get("genres") or [],
            "streaming_providers": m.get("streaming_providers") or [],
            "setting": d.get("setting", {}),
            "archetype": d.get("archetype"),
            "mood": d.get("mood", {}),
            "pacing": d.get("pacing", {}),
            "subjects": d.get("subjects", {}),
            "content_features": d.get("content_features", {}),
            "protagonist_gender": d.get("protagonist_gender"),
            "emotion_dna": d.get("emotion_sparse", {}),
            "theme_dna": d.get("theme_sparse", {}),
            "indexed_at_v3": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            year_int = int(payload["year"]) if payload["year"] else None
        except (TypeError, ValueError):
            year_int = None
        payload["year"] = year_int

        # Build emotion sparse — schema-aware
        emo_dict_raw = d.get("emotion_sparse", {}) or {}
        if schema_v2:
            # F-016: split joint emotion+wirkung into separate L1 buckets.
            # Works on either old (joint) or new (separate) JSONL — splits by
            # tag membership, normalizes each independently.
            emo_only = {t: w for t, w in emo_dict_raw.items() if t in ont_emo_tags}
            wir_only = {t: w for t, w in emo_dict_raw.items() if t in ont_wir_tags}
            emo_normalized = {**_l1(emo_only), **_l1(wir_only)}
        else:
            emo_normalized = emo_dict_raw  # legacy joint-L1 from extract

        # Build theme — schema-aware (v2 has subjects in a separate vector)
        combined_theme = {
            **(d.get("theme_sparse") or {}),
            **(d.get("setting") or {}),
            **(d.get("mood") or {}),
            **(d.get("pacing") or {}),
        }
        if not schema_v2:
            combined_theme.update(d.get("subjects") or {})

        vectors: Dict[str, Any] = {
            "synopsis_dense": emb[i].tolist(),
            "emotion_sparse": to_sparse(emo_normalized, emotion_to_idx),
            "theme_sparse":   to_sparse(combined_theme, theme_to_idx),
        }
        if schema_v2:
            vectors["subject_sparse"] = to_sparse(d.get("subjects") or {}, subject_to_idx)

        points.append(PointStruct(id=tid, vector=vectors, payload=payload))

    client.upsert(collection_name=COLLECTION, points=points, wait=True)
    return len(points)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true", help="drop existing collection")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()

    print("Loading data...")
    movies = json.load(open(SOURCE))
    by_id = {m["tmdb_id"]: m for m in movies}
    dna = load_dna()
    print(f"  movies: {len(movies)}, DNA records: {len(dna)}")

    targets = [m for m in movies if m["tmdb_id"] in dna]
    if args.limit:
        targets = targets[: args.limit]
    print(f"  films to index: {len(targets)}")

    if not targets:
        print("Nothing to index.")
        return

    # Load embedding model. Device picked by `pick_torch_device` honoring the
    # EMBEDDING_DEVICE env var (auto|cuda|cpu). Old GPUs (sm_<70) fall back to
    # CPU automatically.
    from scripts.search_v3 import pick_torch_device
    device = pick_torch_device()
    print(f"Loading {EMBEDDING_MODEL} on {device} ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    print(f"  device: {model.device}")

    # qdrant
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=120.0)
    setup_collection(client, args.recreate)

    schema_v = _schema_version_from_config()
    if schema_v >= 2:
        print(f"Schema v{schema_v}: emotion(separate L1) + theme(no subjects) + subject_sparse")
        emotion_to_idx, theme_to_idx, subject_to_idx = load_ontology_indices_v2()
    else:
        print(f"Schema v{schema_v}: legacy joint-L1 emotion, subjects-in-theme")
        emotion_to_idx, theme_to_idx = load_ontology_indices()
        subject_to_idx = None

    # prepare batches: encode synopsis_dense, build sparse, upsert
    t0 = time.time()
    total_upserted = 0
    n_batches = (len(targets) + args.batch - 1) // args.batch

    for bi in range(n_batches):
        batch = targets[bi * args.batch : (bi + 1) * args.batch]
        texts = [make_synopsis_text(m) for m in batch]
        # E5 wants normalize_embeddings=True for cosine
        emb = model.encode(
            texts,
            batch_size=min(args.batch, 32),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        points = []
        for i, m in enumerate(batch):
            tid = m["tmdb_id"]
            d = dna.get(tid, {}).get("dna_v3", {})
            payload = {
                "tmdb_id": tid,
                "title": m.get("title"),
                "original_title": m.get("original_title"),
                "year": m.get("year") or (m.get("release_date", "")[:4] or None),
                "overview": (m.get("overview") or "")[:500],
                "keywords": (m.get("keywords") or [])[:20],
                "director": m.get("director"),
                "cast": (m.get("cast") or [])[:5],
                "runtime": m.get("runtime") or 0,
                "vote_count": m.get("vote_count") or 0,
                "vote_average": float(m.get("vote_average") or 0.0),
                "popularity": float(m.get("popularity") or 0.0),
                "release_date": m.get("release_date") or "",
                "genres": m.get("genres") or [],  # original TMDB binary list (for hard filter)
                # DNA v3 payload
                "setting": d.get("setting", {}),
                "archetype": d.get("archetype"),
                "mood": d.get("mood", {}),
                "pacing": d.get("pacing", {}),
                "subjects": d.get("subjects", {}),
                "content_features": d.get("content_features", {}),
                "protagonist_gender": d.get("protagonist_gender"),
                # Surface emotion+theme dicts on payload too (for explainability)
                "emotion_dna": d.get("emotion_sparse", {}),
                "theme_dna": d.get("theme_sparse", {}),
                "indexed_at_v3": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            try:
                year_int = int(payload["year"]) if payload["year"] else None
            except (TypeError, ValueError):
                year_int = None
            payload["year"] = year_int

            # Build named vectors — schema-aware
            if schema_v >= 2:
                # F-016: split emotion/wirkung into separate L1
                from scripts.extract_dna_v3 import normalize_l1 as _l1
                ont_emo_tags = set(json.load(open(ONT_DIR / "emotions.json"))["tags"])
                ont_wir_tags = set(json.load(open(ONT_DIR / "wirkung.json"))["tags"])
                emo_raw = d.get("emotion_sparse", {}) or {}
                emo_only = {t: w for t, w in emo_raw.items() if t in ont_emo_tags}
                wir_only = {t: w for t, w in emo_raw.items() if t in ont_wir_tags}
                emo_normalized = {**_l1(emo_only), **_l1(wir_only)}
                # F-017: subjects out of theme_sparse, into separate channel
                combined_theme = {
                    **(d.get("theme_sparse") or {}),
                    **(d.get("setting") or {}),
                    **(d.get("mood") or {}),
                    **(d.get("pacing") or {}),
                }
                vectors = {
                    "synopsis_dense": emb[i].tolist(),
                    "emotion_sparse": to_sparse(emo_normalized, emotion_to_idx),
                    "theme_sparse":   to_sparse(combined_theme, theme_to_idx),
                    "subject_sparse": to_sparse(d.get("subjects") or {}, subject_to_idx),
                }
            else:
                # Legacy v1: theme_sparse spans 6 buckets including subjects
                combined_theme = {
                    **(d.get("theme_sparse") or {}),
                    **(d.get("setting") or {}),
                    **(d.get("mood") or {}),
                    **(d.get("pacing") or {}),
                    **(d.get("subjects") or {}),
                }
                vectors = {
                    "synopsis_dense": emb[i].tolist(),
                    "emotion_sparse": to_sparse(d.get("emotion_sparse", {}), emotion_to_idx),
                    "theme_sparse":   to_sparse(combined_theme, theme_to_idx),
                }
            points.append(PointStruct(id=tid, vector=vectors, payload=payload))

        client.upsert(collection_name=COLLECTION, points=points, wait=False)
        total_upserted += len(points)
        elapsed = time.time() - t0
        rate = total_upserted / max(elapsed, 1e-3)
        eta = (len(targets) - total_upserted) / max(rate, 1e-3)
        print(f"  batch {bi+1}/{n_batches}  upserted={total_upserted}/{len(targets)}  "
              f"rate={rate:.1f}/s  eta={eta:.0f}s")

    # wait for upserts to complete
    print("Waiting for Qdrant to flush...")
    client.upsert(collection_name=COLLECTION, points=[], wait=True) if False else None
    info = client.get_collection(COLLECTION)
    print(f"\nDone. Collection {COLLECTION}: {info.points_count} points  "
          f"indexed_vectors={info.indexed_vectors_count}  status={info.status}")
    print(f"Wallclock: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
