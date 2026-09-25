# Vigilant ESP — Installation Guide

*Step-by-step deployment for licensees. Time budget: ~15 minutes for the
engine, plus catalog-ingest time (~$0.0003/film via OpenAI).*

---

## 1. Prerequisites

| What | Minimum | Recommended |
|---|---|---|
| OS | Linux x86_64 with Docker 24+ | Ubuntu 22.04 LTS |
| RAM | 6 GB free | 16 GB for ≤ 200 K films |
| Disk | 20 GB free (model weights + Qdrant data) | 50 GB SSD |
| Network | outbound HTTPS to `api.openai.com` and `huggingface.co` | — |
| API key | OpenAI account with billing enabled | — |

Optional: NVIDIA GPU with CUDA 12.x for the local-LLM path (Qwen / Llama
3.1 / Mistral via llama-cpp); not required if you use OpenAI.

---

## 2. Get the Code

A licensed copy was delivered as a tarball or git repo. Unpack to any
directory; everything is self-contained.

```bash
cd /opt
tar xzf vigilant-esp-v3.tar.gz
cd vigilant-esp-v3
ls -la
# Should show: Dockerfile, docker-compose.yml, api_v3.py, scripts/,
#              config/, frontend/, requirements.txt, LICENSE, …
```

---

## 3. Configure Environment

```bash
cp .env.example .env
nano .env
```

Set at least:

```env
# Required for LLM intent extraction
OPENAI_API_KEY=sk-proj-...

# Required for /api/admin/* endpoints (comma-separated, generate strong keys)
ADMIN_API_KEYS=key-customer-prod-aBc12...,key-ops-readonly-XyZ98...

# Optional (overrides)
OPENAI_MODEL_DNA=gpt-5-mini          # default; try gpt-5.4-mini for quality
OPENAI_BASE_URL=                     # leave empty for OpenAI; set for Azure/Together/vLLM/Ollama
EMBEDDING_DEVICE=auto                # auto/cuda/cpu
LOCAL_LLM_ENABLED=0                  # 1 to use a GGUF instead of OpenAI
CORS_ORIGINS=https://your-frontend.example.com,https://admin.example.com
TENANT_PROVIDERS_ALLOWED=            # leave empty for "all" providers visible
```

**Generate strong admin keys:**

```bash
python3 -c "import secrets; print('key-prod-' + secrets.token_urlsafe(24))"
```

---

## 4. Start the Stack

```bash
docker compose up -d
```

This pulls `qdrant/qdrant:v1.14.1` and builds the `mindread:v3` image
(first build ~3-5 minutes, subsequent restarts <30 s).

**Verify both containers are healthy:**

```bash
docker compose ps
# NAME              IMAGE                  STATUS
# mindread-api      mindread:v3            Up (healthy)
# mindread-qdrant   qdrant/qdrant:v1.14.1  Up (healthy)
```

**First-start checks:**

```bash
# API responds
curl http://localhost:8000/api/health
# → {"status":"healthy","collection":"mindread_v3","points":0,...}

# Swagger UI for interactive API exploration
open http://localhost:8000/api/docs

# Frontend
open http://localhost:8000/
```

The first request will download the E5-large-v2 embedding model
(~1.3 GB, cached in the `e5_cache` volume — only once).

---

## 5. Load Your Catalog

You have two ways to feed films into the engine.

### A. JSON batch (recommended for programmatic clients)

```bash
curl -X POST http://localhost:8000/api/admin/films \
     -H 'X-API-Key: key-prod-aBc12...' \
     -H 'content-type: application/json' \
     -d @batch.json
```

`batch.json`:

```jsonc
{
  "films": [
    {
      "tmdb_id": 12345,
      "title": "Your Film Title",
      "overview": "Plot synopsis (required, fed to both LLM and E5)…",
      "year": 2024,
      "genres": ["Action","Thriller"],
      "keywords": ["assassin","revenge","new york"],
      "vote_count": 5000,
      "vote_average": 7.4,
      "streaming_providers": ["Netflix"],
      "poster_path": "/your-poster.jpg",
      "title_de": "Optional German Title",
      "overview_de": "Optional German synopsis…"
    }
    // … up to 200 per call
  ],
  "do_index": true,
  "skip_existing": true
}
```

### B. CSV upload (recommended for Excel/Google-Sheet exports)

```bash
curl -X POST http://localhost:8000/api/admin/films/csv \
     -H 'X-API-Key: key-prod-aBc12...' \
     -F 'file=@catalog.csv' \
     -F 'do_index=true'
```

`catalog.csv`:

```csv
tmdb_id,title,overview,year,genres,keywords,vote_count,vote_average,streaming_providers,poster_path
12345,"Your Film","Plot…",2024,Action|Thriller,assassin|revenge,5000,7.4,Netflix,/poster.jpg
```

Pipe-separator for multi-value columns. UTF-8 with optional BOM.

### Bulk-load script for large catalogs

For 50K+ films, batch client-side (the endpoint accepts ≤200/call):

```python
import requests, json, itertools, time

API   = "http://localhost:8000"
TOKEN = "key-prod-aBc12..."

def chunks(it, n):
    it = iter(it)
    while batch := list(itertools.islice(it, n)):
        yield batch

with open("full_catalog.json") as f:
    catalog = json.load(f)

for i, batch in enumerate(chunks(catalog, 200)):
    r = requests.post(f"{API}/api/admin/films",
                       headers={"X-API-Key": TOKEN},
                       json={"films": batch, "do_index": True,
                             "skip_existing": True})
    print(f"Batch {i}: {r.status_code} {r.json().get('status')}")
    time.sleep(1)   # don't hammer OpenAI

requests.post(f"{API}/api/admin/refresh-title-index",
               headers={"X-API-Key": TOKEN})
```

Expected throughput: **~10 films/s** with OpenAI gpt-5.4-mini (LLM-bound).
50 K films ≈ 80 min, ~$15. 200 K films ≈ 5.5 h, ~$60.

---

## 6. Verify Search Works

```bash
# Free-text query
curl -X POST http://localhost:8000/api/search \
     -H 'content-type: application/json' \
     -d '{"query":"feel-good Sci-Fi","limit":5}' | jq .results[].title

# Similarity search (no LLM)
curl -X POST http://localhost:8000/api/search \
     -H 'content-type: application/json' \
     -d '{"similar_to":245891,"limit":5}' | jq .results[].title
```

If both return reasonable films, the engine is live. Open
`http://localhost:8000/` for the bundled Wheel-UI to play with.

---

## 7. Production Hardening Checklist

Before exposing to end-users:

- [ ] Put a reverse proxy in front (nginx/Caddy/Traefik) — terminate TLS,
      enforce rate-limits per IP, restrict `/api/admin/*` to known IPs
- [ ] Set `CORS_ORIGINS` env to your exact frontend origins (not `*`)
- [ ] Rotate `ADMIN_API_KEYS` — keep a current + previous key during transition
- [ ] Configure log shipping (the API uses Python logging — JSON formatter
      can be enabled via `LOG_FORMAT=json` env)
- [ ] Set up Prometheus-style metrics scraping if you want SLO dashboards
      (the engine emits structured logs; a `/metrics` endpoint can be
      enabled via Support-Tier change request)
- [ ] Persist `qdrant_data` volume to durable storage and back it up
      (Qdrant docs cover snapshots: <https://qdrant.tech/documentation/concepts/snapshots/>)
- [ ] Pin Docker images by digest in production compose, not by tag
- [ ] Use a dedicated OpenAI API-Key per tenant for cost attribution
- [ ] Monitor the `pending_reindex` field of `/api/health` — if it grows
      without bound, your extract jobs are running but reindex isn't

---

## 8. Updating / Re-deploying

```bash
git pull              # or extract new tarball over the old
docker compose build api
docker compose up -d
```

Schema migrations (Schema v2 → v3 if ever bumped) are documented in
the changelog of the release. For now, all upgrades are
backwards-compatible — your indexed films remain searchable.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/api/health` returns `degraded` | Qdrant unreachable | `docker compose logs qdrant`; check `QDRANT_HOST` env |
| 401 on `/api/admin/*` | wrong/missing X-API-Key | Match env var `ADMIN_API_KEYS` |
| `LLM call failed (insufficient_quota)` | OpenAI billing | Top up account or set `LOCAL_LLM_ENABLED=1` |
| First request hangs ~30s | E5 model download | One-time; subsequent requests are fast |
| `Too many open files` in Qdrant logs | OS ulimit | Already set in `docker-compose.yml`; ensure host kernel allows nofile=65536 |
| Empty search results | Catalog not loaded | Check `/api/health` → `points` > 0 |
| Slow ingest | LLM rate-limit | Reduce client parallelism, or upgrade OpenAI tier |

---

## 10. Support Contact

License: see [`LICENSE`](LICENSE) (proprietary, commercial).

Bug reports & support tickets: info@vigilant-crs.de — include
`/api/health` output + relevant logs.

Architecture overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
LLM provider swap: [`docs/LLM_PROVIDERS.md`](docs/LLM_PROVIDERS.md).
API reference (interactive): `http://localhost:8000/api/docs`.
End-user UI guide: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).
