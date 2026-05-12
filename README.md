# MindRead V3 — Emotional Movie Search

A search engine for films that understands what you want to *feel*, not just keyword-match.

```
"düstere Rachefilme mit Happy End"  →  John Wick, Wake of Death, Furious 7
"cyberpunk Filme mit Action"        →  Ghost in the Shell, Alita: Battle Angel, RoboCop
"Filme wie Im Auftrag des Teufels"  →  Needful Things, Under Suspicion, Lolita
```

## Tech-Stack

- **Embedding**: `intfloat/multilingual-e5-large` (DE/EN für Synopsis)
- **Vector DB**: Qdrant 1.14 — 1 dense (1024-dim cosine) + 2 sparse (emotion 30-dim L1=1, theme 88-dim L1=1)
- **LLM (Intent extraction)**: OpenAI gpt-5.4-mini (default) | Mistral | Anthropic | local Qwen — switchable
- **Fusion**: Reciprocal Rank Fusion across 3 channels (+ optional 4th personal channel)
- **Backend**: FastAPI (~400 lines)
- **Frontend**: vanilla JS + SVG Plutchik-Wheel (~600 lines)
- **DNA**: 128 canonical ontology tags (24 Plutchik emotions + 6 viewer impacts + 35 plot themes + 18 genres + 15 settings + 10 archetypes + 12 moods + 8 pacing)

## Project Structure

```
api_v3.py                  ← FastAPI server (entry point)
frontend/index.html        ← SPA with Wheel UI
config/ontology_v3/        ← 128-tag ontology + synonyms + definitions
scripts/
  extract_dna_v3.py        ← LLM-based DNA extraction (default: gpt-5.4-mini)
  reindex_v3.py            ← (Re)build Qdrant collection
  search_v3.py             ← Hybrid search with RRF fusion
  fetch_tmdb_v3.py         ← TMDB bulk fetcher
  enrich_payload_tmdb.py   ← Adds posters, vote_count, popularity
  enrich_providers_tmdb.py ← Adds streaming_providers per region
  llm_local.py             ← Qwen-via-llama-cpp adapter
  eval_v3.py               ← Quality eval suite
docs/
  USER_GUIDE.md            ← End-user UI documentation
  API_GUIDE.md             ← Integration guide for developers
PRODUCTIZATION_BRIEF.md    ← B2B sales doc (Magenta TV / Maxdome)
```

## Run It

```bash
# 1. Qdrant
docker compose up -d qdrant

# 2. Extract DNA (one-time, ~$25 OpenAI for 7K films)
venv/bin/python3 scripts/extract_dna_v3.py --workers 20

# 3. Reindex to Qdrant
CUDA_VISIBLE_DEVICES="" venv/bin/python3 scripts/reindex_v3.py --recreate

# 4. Enrich with posters + providers
venv/bin/python3 scripts/enrich_payload_tmdb.py
venv/bin/python3 scripts/enrich_providers_tmdb.py --region DE

# 5. Start API + UI
CUDA_VISIBLE_DEVICES="" venv/bin/python3 -m uvicorn api_v3:app --host 0.0.0.0 --port 8000
# → http://localhost:8000/
```

## Environment

| var | purpose |
|:--|:--|
| `OPENAI_API_KEY` | Default LLM provider |
| `TMDB_API_KEY` | Bulk fetch + enrichments |
| `LOCAL_LLM_ENABLED=1` | Use local Qwen instead of OpenAI |
| `LOCAL_LLM_SIZE=2b\|4b` | Which Qwen GGUF to load |
| `TENANT_PROVIDERS_ALLOWED="Magenta TV+,DAZN"` | Restrict provider list per tenant |

## Documentation

- [User Guide (UI)](docs/USER_GUIDE.md)
- [API Guide (developer integration)](docs/API_GUIDE.md)
- [Productization Brief (B2B sales)](PRODUCTIZATION_BRIEF.md)

## Status (2026-05-04)

- ✅ Live: 7018 Filme, multilingual, hybrid-Search
- 🔄 In progress: 14K weitere Filme von TMDB → DNA-Extract → Reindex (geplant)
- 🔄 GPU-Treiber-Fix nötig für lokales Qwen-Live (sudo-Job, dann llama-cpp mit CUDA neu bauen)
- ⏳ Open: Mobile UI, Onboarding-Tour, Authentication
