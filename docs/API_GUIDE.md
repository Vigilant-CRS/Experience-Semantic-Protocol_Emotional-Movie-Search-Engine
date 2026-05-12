# MindRead V3 — API Integration Guide

REST-API für Streaming-Anbieter. Stand 2026-05-12.

**Engine = Software, kein SaaS.** Käufer hostet selbst, bringt seinen Katalog mit, baut die API in seine bestehende UI ein. Multi-Tenancy, Auth und Rate-Limiting sind **bewusst nicht Teil der Engine** — werden vom Käufer in seiner eigenen Infrastruktur (API-Gateway, Reverse-Proxy) abgehandelt.

**Live OpenAPI-Schema:** `GET /api/docs` (Swagger UI) — vollautomatisch aus Pydantic-Modellen.

---

## Inhaltsverzeichnis

1. [Schnellstart](#schnellstart)
2. [Endpoint-Übersicht](#endpoint-übersicht)
3. [Such-Endpoints](#such-endpoints) — `/api/search`, Wheel-Adjust, Personalisierung
4. [Admin-Endpoints](#admin-endpoints) — Plug-and-Play Ingest
5. [Read-Only-Endpoints](#read-only-endpoints) — Health, Providers, Ontology
6. [Konfiguration](#konfiguration) — Env, engine_params.yaml
7. [Performance-Profile](#performance)

---

## Schnellstart

```bash
# Service starten
docker compose up -d   # qdrant
uvicorn api_v3:app --host 0.0.0.0 --port 8000

# Health prüfen
curl http://localhost:8000/api/health

# Suche
curl -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"düstere Rachegeschichte mit Happy End","limit":10}'

# Eigene Filme einspielen
curl -X POST http://localhost:8000/api/admin/films \
  -H 'Content-Type: application/json' \
  -d '{"films":[{"tmdb_id":1,"title":"...","overview":"..."}]}'
```

---

## Endpoint-Übersicht

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/health` | Status + Korpus-Zahlen |
| GET | `/api/ontology?lang=de\|en` | 162 Tags + Definitionen + Synonyme |
| GET | `/api/providers` | Liste der Streaming-Provider mit Filmzahlen |
| GET | `/api/film/{tmdb_id}` | Vollständiger Film-Payload (DNA, Provider, etc.) |
| **POST** | **`/api/search`** | **Haupt-Such-Endpoint** |
| POST | `/api/admin/films` | Plug-and-Play Ingest (Käufer-Katalog hochladen) |
| POST | `/api/admin/refresh-title-index` | Title-Cache nach Bulk-Ingest neu aufbauen |
| GET | `/api/docs` | Swagger UI |
| GET | `/openapi.json` | OpenAPI 3.1 Spec |

---

## Such-Endpoints

### `POST /api/search`

**Body — `query` ODER `similar_to` Pflicht, alles andere optional:**

```jsonc
{
  // Auswahl-Modus (eines von beiden Pflicht)
  "query": "Filme wie John Wick aber lustiger",
  "similar_to": null,                  // ODER tmdb_id

  "limit": 10,                         // 1..50

  // Slider — Channel-Gewichte (default 0.35/0.35/0.30)
  "w_synopsis": 0.35,                  // E5 dense (semantic synopsis match)
  "w_emotion": 0.35,                   // emotion_sparse (Plutchik + Wirkung)
  "w_theme": 0.30,                     // theme_sparse (themes+genres+settings+moods+pacing+subjects)

  // Slider — Indie ↔ Mainstream (-1..+1)
  "indie_mainstream": 0.0,

  // Hard-Filter
  "year_min": 1990,
  "year_max": 2024,
  "runtime_min": 60,                    // default 60 → keine Featurettes
  "runtime_max": null,
  "min_vote_count": 0,
  "genre": ["Action", "Thriller"],     // TMDB genre keyword match
  "gender": "male",                     // male|female|ensemble|non_binary
  "streaming_providers": ["Netflix"],  // film must be on at least one

  // Avoid (3 Mechanismen, siehe DECISIONS D-011)
  "avoid_emotions": ["disgust"],       // soft-penalty
  "avoid_themes": [],                  // soft-penalty
  "avoid_content": ["firearms"],       // HARD must_not on payload.content_features.*
  "avoid_strict": false,               // when true, emotions/themes also become hard

  // Display
  "lang": "en",                         // en|de — translates match-reason tag labels

  // Wheel-only: kein LLM-Call, nutze direkt diese Vektoren (Latency ~50ms)
  "adjusted_emotions": null,           // {tag: weight, ...}
  "adjusted_themes": null,             // {tag: weight, ...} (covers themes+settings+moods+pacing+subjects)

  // Personalisierung A — Server averaged DNA der gelikten Filme
  "liked_tmdb_ids": [],                // up to 50 tmdb_ids
  "w_personal": 0.0,                    // 0..1

  // Personalisierung B — externes Customer-ML übergibt Scores
  "external_score_boost": {},          // {tmdb_id: 0..1}
  "w_external": 0.0                     // 0..2
}
```

**Response (gekürzt):**

```jsonc
{
  "query": "Filme wie John Wick aber lustiger",
  "similar_to": null,
  "reference_title": "John Wick",       // wenn LLM "wie X" aufgelöst hat
  "intent": {                            // was der LLM extrahiert hat (nur free-text)
    "emotion_sparse": {"joy": 0.5, "amusement": 0.5},
    "theme_sparse":   {"Comedy": 1.0},
    "avoid_emotions": [],
    "avoid_themes": [],
    "avoid_content": [],
    "similar_to_title": "John Wick",
    "protagonist_gender": null,
    "year_min": null,
    "year_max": null
  },
  "weights_used": {"w_synopsis": 0.35, "w_emotion": 0.35, "w_theme": 0.30},
  "results": [
    {
      "tmdb_id": 245891,
      "title": "John Wick",
      "year": 2014,
      "overview": "...",
      "score": 0.0231,
      "channels": {"synopsis": 0.83, "emotion": 0.18, "theme": 0.16},
      "genres": ["Action", "Thriller"],
      "archetype": "antihero",
      "protagonist_gender": "male",
      "runtime": 101,
      "vote_count": 14829,
      "vote_average": 7.4,
      "popularity": 35.6,
      "poster_path": "/...jpg",
      "backdrop_path": "/...jpg",
      "emotion_dna": {"cathartic": 0.35, "rage": 0.15, "grief": 0.10},
      "theme_dna":   {"Action": 0.30, "revenge": 0.25},
      "setting":     {"urban_modern": 0.70, "criminal_underworld": 0.30},
      "mood":        {"dark": 0.50, "gritty": 0.30, "noir": 0.20},
      "pacing":      {"action_packed": 0.70, "fast_paced": 0.30},
      "streaming_providers": ["Netflix", "WOW"],
      "match_emotions": [
        {"tag": "cathartic", "query_weight": 0.22, "film_weight": 0.35, "contribution": 0.077}
      ],
      "match_themes":   [...]
    }
  ],
  "search_time_ms": 2150
}
```

### Such-Patterns

#### A. Free-Text mit LLM-Intent
```python
requests.post(URL, json={"query": "düstere Rachefilme mit Happy End", "limit": 10})
```

#### B. „Wie dieser Film"
```python
requests.post(URL, json={"similar_to": 245891, "limit": 10, "indie_mainstream": -0.3})
```

#### C. „Wie X aber Y" (Tone-Shift)
LLM erkennt Modifier, lädt Reference-DNA aus dem Index, blendet (config-gesteuert, default 60% Reference + 40% Modifier).
```python
requests.post(URL, json={"query": "Filme wie Amélie aber mit mehr Action"})
# → reference_title="Amélie", results = Action-getönte Whimsy-Filme
```

#### D. Avoid Content-Features
Hard-Filter via Qdrant `must_not` auf `payload.content_features.X > 0`. 10 verfügbare Tags: `firearms, bladed_weapons, physical_combat, explosions, supernatural_combat, vehicular_combat, graphic_violence, torture, sexual_content, drug_use`.
```python
requests.post(URL, json={"query": "Action für Kinder",
                          "avoid_content": ["graphic_violence","torture","sexual_content","drug_use"]})
```

#### E. Wheel-Adjust ohne LLM (~50ms statt 2-3s)
Nach erster Suche kennt der Client `intent.emotion_sparse` und `intent.theme_sparse`. Slider/Wheel-Anpassung sendet diese direkt:
```python
requests.post(URL, json={
  "query": "Rachefilme",  # nur für Kontext
  "adjusted_emotions": {"rage": 0.4, "cathartic": 0.3, "grief": 0.3},
  "adjusted_themes":   {"revenge": 0.7, "Action": 0.3}
})
```

#### F. Personalisierung via User-Profil
```python
# A: Server mittelt DNA der gelikten Filme
requests.post(URL, json={"query": "...", "liked_tmdb_ids": [245891, 1813, 194], "w_personal": 0.6})

# B: Customer übergibt eigene ML-Scores
requests.post(URL, json={"query": "...", "external_score_boost": {245891: 0.95, 1813: 0.88}, "w_external": 1.5})
```

---

## Admin-Endpoints

Diese Endpoints sind **nicht für End-User**. Vom Käufer-Backend aufgerufen (z.B. nightly catalog sync). Wenn die Engine direkt im Internet exponiert wird, sollte der Käufer sie per Reverse-Proxy / API-Gateway abriegeln.

### `POST /api/admin/films` — Plug-and-Play Ingest

Akzeptiert bis zu **200 Filme pro Call**. Bei größeren Katalogen den Client batchen lassen.

**Body:**
```jsonc
{
  "films": [
    {
      "tmdb_id": 12345,              // unique customer-side int ID (kann auch eigene CMS-ID sein)
      "title": "Film Title",
      "overview": "Plot synopsis...",  // ERFORDERLICH — speist E5 + LLM
      "original_title": null,
      "year": 2024,
      "release_date": "2024-03-15",
      "runtime": 110,
      "genres": ["Action","Thriller"],
      "keywords": ["assassin","revenge"],
      "director": "Director Name",
      "cast": ["Actor 1", "Actor 2"],
      "vote_count": 5000,
      "vote_average": 7.4,
      "popularity": 35.6,
      "poster_path": "/abc.jpg",
      "backdrop_path": "/xyz.jpg",
      "streaming_providers": ["Netflix"],
      "title_de": "Deutscher Titel",
      "overview_de": "Deutsche Synopsis..."
    }
  ],
  "use_local_llm": null,            // null=inherit env, true=force Qwen, false=force OpenAI
  "do_index": true,                  // upsert to Qdrant after extract
  "skip_existing": true              // idempotent re-runs
}
```

**Response:**
```jsonc
{
  "status": "ok",                    // ok | partial | nothing_to_do
  "received": 200,
  "extracted": 195,
  "indexed": 195,
  "skipped_existing": 0,
  "errors": [
    {"tmdb_id": 999, "title": "...", "error": "JSONDecodeError: ..."}
  ],
  "elapsed_ms": 145000
}
```

**Customer-Flow für 50K Filme:**
```python
for chunk in chunked(catalog, 200):
    r = requests.post(URL + "/api/admin/films",
                       json={"films": chunk, "do_index": True})
    print(r.json())   # check errors per batch
requests.post(URL + "/api/admin/refresh-title-index")  # einmal am Ende
```

**Welcher LLM wird benutzt?**
- `use_local_llm: null` (default) → respektiert `LOCAL_LLM_ENABLED` env beim Server-Start
- `use_local_llm: true` → Qwen GGUF lokal (braucht `LOCAL_LLM_MODEL_DIR` env gesetzt)
- `use_local_llm: false` → OpenAI (braucht `OPENAI_API_KEY` env)

Speed-Erwartung pro Film:
- OpenAI gpt-5-mini: **1-2 s/Film** mit Prompt-Caching
- Lokales Qwen 4B auf Quadro P620: **50-80 s/Film** (zu langsam für Synchron-Ingest, eher Batch-CLI nutzen)
- Lokales Qwen 4B auf RTX 4090: **3-8 s/Film** (synchron praktikabel)

### `POST /api/admin/refresh-title-index`

Baut den In-Memory-Title-Cache (für „wie X"-Auflösung) neu aus Qdrant. Nach größeren Ingests aufrufen.

```jsonc
// Response:
{"status": "ok", "title_keys": 7837, "films": 7018}
```

---

## Read-Only-Endpoints

### `GET /api/health`
```jsonc
{
  "status": "healthy",
  "collection": "mindread_v3",
  "points": 7018,
  "indexed_vectors": 14028,
  "extracted_total": 14984,           // films in JSONL (incl. not-yet-indexed)
  "pending_reindex": 7966,             // extracted but not in Qdrant
  "ontology_buckets": {
    "emotions": 24, "wirkung": 6, "plot_themes": 35, "genres": 18,
    "settings": 15, "archetypes": 10, "moods": 12, "pacing": 8,
    "subjects": 24, "content_features": 10
  },
  "llm": "gpt-5-mini",
  "tenant_providers_allowed": "all"
}
```

### `GET /api/ontology?lang=en|de`
Liefert komplette Ontology + Synonyms + (falls `lang=de`) deutsche Labels für alle 162 Tags. Zum Bauen eines eigenen Wheel-UIs.

### `GET /api/providers`
Liste der `streaming_providers` Keywords mit Filmzahlen im aktuellen Index.

### `GET /api/film/{tmdb_id}`
Vollständiger Payload eines indexierten Films — alle DNA-Felder, Provider, etc.

---

## Konfiguration

### Environment Variables

| Variable | Default | Zweck |
|---|---|---|
| `QDRANT_HOST` | `localhost` | Qdrant-Hostname |
| `QDRANT_PORT` | `6333` | Qdrant-HTTP-Port |
| `QDRANT_COLLECTION_V3` | `mindread_v3` | Collection-Name |
| `EMBEDDING_MODEL` | `intfloat/e5-large-v2` | HF-Modellname für E5 |
| `EMBEDDING_DEVICE` | `auto` | `auto`/`cuda`/`cpu` für E5-Embedding |
| `OPENAI_API_KEY` | — | Für OpenAI-Pfad |
| `OPENAI_MODEL_DNA` | `gpt-5-mini` | Welches OpenAI-Modell |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-kompatibler Endpoint |
| `LOCAL_LLM_ENABLED` | `0` | `1` → nutze Qwen lokal statt OpenAI für `/api/search` |
| `LOCAL_LLM_GGUF` | — | Exakter Pfad zum GGUF-Modell (höchste Priorität) |
| `LOCAL_LLM_MODEL_DIR` | — | Verzeichnis für Auto-Discovery der GGUFs |
| `LOCAL_LLM_SIZE` | `2b` | `2b` oder `4b` für Auto-Discovery |
| `LOCAL_LLM_THREADS` | `12` | llama-cpp CPU-Threads |
| `LOCAL_LLM_N_GPU_LAYERS` | `0` | Layer-Anzahl auf GPU (999 = alle) |
| `LOCAL_LLM_CTX` | `8192` | Kontext-Größe |
| `CORS_ORIGINS` | `*` | Komma-getrennte Liste oder `*`. Bei `*` wird `allow_credentials` automatisch deaktiviert (Browser-Spec) |
| `TENANT_PROVIDERS_ALLOWED` | — | Optional: Komma-Liste der Provider zu denen sich der Tenant beschränken will |

### `config/engine_params.yaml`

Zentrale Konfiguration aller Retrieval-/Scoring-Parameter. Jeder Wert mit theoretischer Begründung. Auszug:

```yaml
retrieval:
  default_weights:
    w_synopsis: 0.35
    w_emotion:  0.25
    w_theme:    0.25
    w_subject:  0.15      # geplant für separate subject channel
  over_fetch_multiplier: 20

fusion:
  algorithm: weighted_rrf
  rrf_k: 60

avoid:
  soft_penalty_factor: 0.5
  soft_score_magnitude: 0.02
  strict_threshold: 0.10

tone_shift:
  reference_weight: 0.6
  modifier_weight: 0.4
  renormalize_l1: true

popularity_boost:
  scale: 0.01
  indie_min_quality_va: 7.0

synonym:
  decay: 0.7

diversify:
  enabled: true
  demotion_strength: 0.4
  max_per_franchise: 2
  ref_franchise_cap_multiplier: 2
```

API-Restart nach Änderung erforderlich.

---

## Performance

Gemessen auf Demo-Hardware (Quadro P620, sm_61 → E5 auf CPU; Käufer-GPU mit sm_70+ → E5 automatisch CUDA).

| Use-Case | Latenz | Bottleneck |
|---|---:|---|
| `/api/health` | 5-20 ms | Qdrant collection-info |
| `/api/search` similar_to (kein LLM) | 100-300 ms | 3 Channel × Qdrant |
| `/api/search` mit `adjusted_emotions/themes` (kein LLM) | 80-150 ms | 3 Channel × Qdrant |
| `/api/search` free-text mit OpenAI | **2.0-3.5 s** | OpenAI LLM ~85 % der Zeit |
| `/api/search` free-text mit Qwen 4B P620 | 50-80 s | Quadro P620 zu schwach für Runtime |
| `/api/admin/films` 1 Film (OpenAI) | 1-2 s + Index | LLM-Call |
| `/api/admin/films` 1 Film (Qwen GPU) | 5-80 s + Index | je nach Customer-GPU |
| Reindex 21K Filme (E5 CPU) | ~75 min | E5-Encoding |
| Reindex 21K Filme (E5 GPU sm_70+) | ~10-15 min | E5-Encoding |

**Concurrency:** Standard-Start ist Single-Worker. Für höhere Last:
```bash
uvicorn api_v3:app --host 0.0.0.0 --port 8000 --workers 4
# Achtung: jeder Worker lädt E5 separat (~1.4 GB RAM pro Worker).
```

---

## Versionierung

- Aktuelle API-Version: **3.0.0** (engine-version-string im `/api/health.collection`)
- Breaking Changes nur bei Major-Bumps
- OpenAPI 3.1 unter `/openapi.json`

---

## Käufer-Integration: Typische Schritte

1. **Docker-Compose-Bundle** (api + qdrant) auf Käufer-Server deployen
2. **Konfig**: `config/engine_params.yaml` und Env-Vars für LLM-Provider setzen
3. **Initial-Ingest**: Käufer-Katalog via `/api/admin/films` einspielen (200er-Batches)
4. **Periodisch**: `/api/admin/refresh-title-index` nach Bulk-Updates
5. **Käufer-UI** spricht `/api/search` direkt. Optional: unser Demo-Frontend auf `/` als Vorlage für eigene UI.
6. **Monitoring**: `/api/health` für Liveness, Latenzen via Reverse-Proxy-Logs.
