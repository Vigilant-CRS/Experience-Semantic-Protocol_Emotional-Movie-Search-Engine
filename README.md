# Vigilant ESP — Experience Semantic Protocol

*Reference implementation of the Vigilant Experience Semantic Protocol —
the emotional movie discovery engine for streaming providers. Internal
engine codename: **MindRead V3**.*

Plug-and-Play software for streaming providers. Search films by **how they feel**, not just keywords.

```
"düstere Rachefilme mit Happy End"        →  John Wick, Wake of Death, Furious 7
"Filme wie Amélie aber mit mehr Action"    →  Run Lola Run, Big Fish, Hugo
"Mafiafilme aus den 90ern"                 →  Goodfellas, Casino, Donnie Brasco
"feel-good Sci-Fi"                         →  Wall-E, The Martian, Back to the Future
```

## What this is

A **search engine you embed in your own UI**. Customer brings their catalog, we provide the engine. Not SaaS — software license. Customer hosts on their infrastructure.

| | |
|---|---|
| Deployment | 1-Command Docker bundle: `docker compose up -d` |
| Ingest | `POST /api/admin/films` — feed in your catalog, get back search-ready vectors |
| Query | `POST /api/search` — natural-language → ranked results |
| LLM-Provider | OpenAI (default) or local Qwen via llama-cpp — switchable |
| GPU | Optional. E5 + Qwen both auto-detect CUDA when `sm_70+` available |
| Auth / Multi-Tenant | Out-of-scope by design — customer handles in API gateway |

## Quickstart (1-Command)

```bash
cp .env.example .env       # set OPENAI_API_KEY (or LOCAL_LLM_ENABLED=1)
docker compose up -d       # starts qdrant + api in detached mode
docker compose logs -f api # watch startup (~60s for E5 model download)
```

Then:
- **http://localhost:8000** — demo frontend (Wheel UI)
- **http://localhost:8000/api/docs** — interactive API explorer (Swagger)
- **http://localhost:8000/api/health** — status

## Ingesting your catalog

```python
import requests, json
films = [
    {"tmdb_id": 1, "title": "...", "overview": "...", "year": 2024, ...},
    # up to 200 per call
]
r = requests.post("http://localhost:8000/api/admin/films",
                   json={"films": films, "do_index": True})
print(r.json())   # {"extracted": 200, "indexed": 200, "elapsed_ms": 220000}
```

For 50K films: batch into 250 chunks of 200; total wall-clock ~6 hours via OpenAI gpt-5-mini (depends on rate limits).

## Architecture

| Component | Role |
|---|---|
| `api_v3.py` | FastAPI service: `/api/search`, `/api/admin/films`, `/api/ontology`, `/api/film/{id}`, `/api/health` |
| `frontend/index.html` | SPA demo: Plutchik Wheel + Sliders. Customer may use directly or build their own |
| `config/ontology_v3/` | 162 canonical tags + synonyms + definitions + DE translations |
| `config/engine_params.yaml` | All tunable retrieval/scoring constants in one place |
| `scripts/extract_dna_v3.py` | LLM-based DNA extraction (OpenAI or local Qwen) |
| `scripts/reindex_v3.py` | Build/rebuild Qdrant collection from JSONL |
| `scripts/search_v3.py` | Hybrid retrieval — RRF over 3 channels |
| `scripts/llm_local.py` | Qwen via llama-cpp-python adapter |
| `scripts/eval_v3.py` | 29-test quality suite |
| `Dockerfile` | CPU-only multi-stage build, optional CUDA stage commented in |
| `docker-compose.yml` | api + qdrant + named volumes |
| `docs/API_GUIDE.md` | Full integration guide |

## Architecture

Full diagrams + request-path sequence + measured latency numbers in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Quick overview:

```
Browser/Client → /api/search → FastAPI → LLM (intent extract)
                                    └─→ E5 (encode query text)
                                    └─→ Qdrant (hybrid weighted-RRF)
                                    └─→ post-fusion: avoid, filters, palette boost
```

Measured P95 (15K-film demo corpus, single CPU node):
- `similar_to=id` (no LLM): **153 ms**
- topic query (1 LLM call): **3.6 s**
- cached intent / wheel-adjust (no LLM): **286 ms**
- tone-shift "wie X aber Y" (2 LLM calls, Variant Z): **9 s**

## Retrieval Architecture

Three orthogonal vectors per film (all in Qdrant):

| Vector | Dim | What it captures |
|---|---|---|
| `synopsis_dense` | 1024 | E5-large-v2 semantic embedding of overview text |
| `emotion_sparse` | 30 | Plutchik 8×3 emotions + 6 viewer-impact tags (separately L1-normalized, schema v2) |
| `theme_sparse` | 88 | plot_themes(35) + genres(18) + settings(15) + moods(12) + pacing(8) |
| `subject_sparse` | 24 | subjects (dedicated channel with own slider weight, schema v2) |

Plus payload-only fields: archetype, protagonist_gender, protagonist_age (6 buckets), color_palette (6 buckets, weighted), content_features (10 advisories), streaming_providers, etc.

Fusion via **weighted Reciprocal Rank Fusion** (Cormack 2009 extension) — each channel's top-K combined with slider weights. User can dial the mix.

## Configuration

| Env var | Default | What |
|---|---|---|
| `OPENAI_API_KEY` | — | required for OpenAI LLM path |
| `EMBEDDING_DEVICE` | `auto` | `auto`/`cuda`/`cpu` for E5. Auto picks CUDA on sm_70+ GPUs |
| `LOCAL_LLM_ENABLED` | `0` | `1` → use local Qwen for `/api/search` (needs `LOCAL_LLM_MODEL_DIR`) |
| `LOCAL_LLM_MODEL_DIR` | — | directory containing GGUF model files |
| `LOCAL_LLM_SIZE` | `2b` | `2b` or `4b` — which Qwen variant to auto-pick from MODEL_DIR |
| `CORS_ORIGINS` | `*` | comma-separated origins for production |

All retrieval parameters live in **`config/engine_params.yaml`** with documented rationale. Edit + restart, no code changes.

Full reference: [`docs/API_GUIDE.md`](docs/API_GUIDE.md)

## Quality Eval

```bash
docker compose exec api python scripts/eval_v3.py
# 29 tests covering similar_to, free-text, tone-shift, avoid filters, etc.
# Currently passes 23-26/29 (LLM non-determinism causes ±5% variance)
```

## Dev Setup (without Docker)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in
docker compose up -d qdrant
uvicorn api_v3:app --host 0.0.0.0 --port 8000
```

## Status

- ✅ 15,255 films indexed (demo corpus only — customer brings their own)
- ✅ Schema v2: emotion/wirkung separately L1-normalized + subjects as own channel
- ✅ Plug-and-Play ingest endpoint
- ✅ Docker bundle
- ✅ Engine config externalized to YAML
- ✅ Auto GPU/CPU device selection
- ✅ Engine swappable: OpenAI / local Qwen / any OpenAI-compatible endpoint

## License

Vigilant ESP is **proprietary commercial software**. See [`LICENSE`](LICENSE).
Evaluation copies are not redistributable. For commercial licensing:
dulovic.damir@gmail.com.

Third-party components (Qdrant, FastAPI, sentence-transformers, E5,
PyTorch, Qwen, llama.cpp, OpenAI API, TMDB data, …) are used under
their own licenses, listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

### Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB.
TMDB attribution and logo are displayed in the bundled frontend per
TMDB's API Terms of Use §6.

See also [`PRODUCTIZATION_BRIEF.md`](PRODUCTIZATION_BRIEF.md) for the B2B sales context.
