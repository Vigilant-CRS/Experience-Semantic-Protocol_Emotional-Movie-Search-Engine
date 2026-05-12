# Facts

## Audit-Status 2026-05-12

Hartes dateiübergreifendes Audit durchgeführt (siehe CROSS_MODEL_REVIEW.md CMR-002). 25 Findings dokumentiert, davon 4 kritisch (F-001, F-005 latent, F-010, F-025), 7 hoch.



Objektive, überprüfbare Wahrheiten. Wenn etwas nicht überprüfbar ist, gehört es nicht hierher sondern in `HYPOTHESES.md`.

## Infrastruktur

- API: FastAPI, läuft via uvicorn auf `0.0.0.0:8000`
- Qdrant: docker compose service `qdrant`, port 6333, collection `mindread_v3`
- Frontend: SPA aus `frontend/index.html`, served at `/` und Static via `/static`
- Python venv: `venv/` im Repo-Root

## Korpus-Zahlen (2026-05-11)

- Qdrant points: **7,018** (alte DNA, ohne subjects/content_features)
- JSONL-Zeilen `data/movies_dna_v3.jsonl`: **11,085**
- Pending reindex: **4,067** (im JSONL aber nicht in Qdrant)
- Source-Korpus: **21,418** Filme in `data/movies_top20k.json`
- Fehlend (komplett): **~10,333** Filme

## Ontologie-Größen

| Bucket | Tags | Storage |
|---|---|---|
| emotions | 24 | emotion_sparse[0..23] |
| wirkung | 6 | emotion_sparse[24..29] |
| plot_themes | 35 | theme_sparse[0..34] |
| genres | 18 | theme_sparse[35..52] |
| settings | 15 | theme_sparse[53..67] |
| moods | 12 | theme_sparse[68..79] |
| pacing | 8 | theme_sparse[80..87] |
| subjects | 24 | theme_sparse[88..111] |
| archetypes | 10 | payload single value |
| content_features | 10 | payload weighted dict (NOT in any sparse vector) |
| protagonist_gender | 4 enum | payload single value |

**Total Sparse Dimensionen:** emotion=30, theme=112

## API-Endpoints

- `GET /api/health` — `{points, indexed_vectors, extracted_total, pending_reindex, ontology_buckets, llm, tenant_providers_allowed}`
- `POST /api/search` — Haupt-Endpoint
- `GET /api/providers` — Liste der Streaming-Provider mit Filmzahlen
- `GET /api/ontology?lang=de|en` — Tag-Vokabular + Übersetzungen
- `GET /api/film/{tmdb_id}` — Einzelner Film payload

## SearchRequest Felder (aktuelle Schema)

`query` (str), `similar_to` (tmdb_id int), `limit` (int), Slider: `w_synopsis`, `w_emotion`, `w_theme`, `w_personal`, `w_external` (alle [0,1]), `indie_mainstream` ([-1,1]), Filter: `year_min`/`max`, `runtime_min`/`max`, `min_vote_count`, `genre[]`, `gender`, `avoid_emotions[]`, `avoid_themes[]`, `avoid_content[]`, `avoid_strict` (bool), `streaming_providers[]`, `lang` (de|en), Wheel-Override: `adjusted_emotions{}`, `adjusted_themes{}`, Profile: `liked_tmdb_ids[]`, `external_score_boost{}`.

## Models

- E5-Embedding: `intfloat/e5-large-v2`, 1024-dim, normalized, cosine similarity
- LLM (runtime): OpenAI `gpt-5.4-mini` over `https://api.openai.com/v1/chat/completions`
- LLM (batch local): Qwen3.5-4B Q5_K_M GGUF (3.0 GB) via llama-cpp-python (CUDA build)
- GGUF-Pfad: `/media/dd/USB_4028/Projekte/Temp/Vigilant-Models/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q5_K_M.gguf`

## Hardware (Dev-Setup)

- GPU: Quadro P620, 4034 MiB VRAM, Compute Capability 6.1
- CUDA Driver 580.126.20, CUDA Toolkit 12.0 (nvcc)
- numpy gepinnt auf `<2` (sklearn-Kompatibilität)

## Eval

- Test-Suite: `scripts/eval_v3.py`, 29 Tests
- Aktuelle Pass-Rate: 25-26/29 (86-90%), Varianz ±5% durch LLM-Non-Determinismus bei T=0.1
- Letztes Ergebnis-JSON: `data/eval_results_assessment.json`

## Datenfluss (kurz)

1. `data/movies_top20k.json` → `extract_dna_v3.py` → `data/movies_dna_v3.jsonl`
2. JSONL → `reindex_v3.py` → Qdrant `mindread_v3`
3. Enrichment: `scripts/fetch_tmdb_*` für Poster, Provider, DE-Titel/Overviews
4. Query: `POST /api/search` → LLM-Intent → Filter + Sparse + Dense → manual_weighted_fusion (RRF) → Re-Rank → Response
