# MindRead — API Integration Guide

REST-API für Streaming-Anbieter und Drittentwickler. Stand 2026-05-04.

Live OpenAPI-Doku: `GET /api/docs` (Swagger UI).

---

## Endpoints

### `GET /api/health`
Health/Status-Check inkl. wie viele Filme indexiert sind.

```bash
curl http://localhost:8000/api/health
```

### `GET /api/ontology`
Liefert alle 128 Tags + Definitionen + Synonyme — z.B. um eigene Wheel-UI zu bauen.

### `GET /api/providers`
Liste aller Streaming-Provider (mit Filmzahl) im Index.

```bash
curl http://localhost:8000/api/providers
# → { "providers": [{"name": "Magenta TV+", "film_count": 193}, ...] }
```

Bei tenant-deployment (`TENANT_PROVIDERS_ALLOWED` env gesetzt) sind hier nur die
erlaubten Provider sichtbar.

### `GET /api/film/{tmdb_id}`
Einzelner Film mit kompletter DNA + Payload.

### `POST /api/search`  ← der Hauptendpoint

**Body** (alle Felder optional, aber `query` ODER `similar_to` Pflicht):

```json
{
  "query": "Filme wie John Wick aber lustiger",
  "limit": 10,

  "w_synopsis": 0.5,
  "w_emotion": 0.3,
  "w_theme": 0.2,
  "indie_mainstream": 0.0,
  "year_min": 2000,
  "runtime_min": 60,

  "genre": ["Action", "Thriller"],
  "gender": "male",
  "streaming_providers": ["Magenta TV+", "Netflix"],

  "avoid_emotions": ["disgust"],
  "avoid_themes": [],
  "avoid_strict": false,

  "similar_to": null,
  "adjusted_emotions": null,
  "adjusted_themes": null,

  "liked_tmdb_ids": [],
  "w_personal": 0.0,

  "external_score_boost": {},
  "w_external": 0.0
}
```

### Response

```json
{
  "query": "...",
  "reference_title": "The Devil's Advocate",   // wenn similar_to_title aufgelöst
  "intent": {                                    // was der LLM extrahiert hat
    "emotion_sparse": {"rage": 0.15, "cathartic": 0.30, ...},
    "theme_sparse":   {"revenge": 0.25, "Action": 0.30, ...},
    "avoid_emotions": [],
    "avoid_themes": [],
    "similar_to_title": "The Devil's Advocate"
  },
  "weights_used": {"w_synopsis": 0.5, "w_emotion": 0.3, "w_theme": 0.2},
  "results": [
    {
      "tmdb_id": 245891,
      "title": "John Wick",
      "year": 2014,
      "overview": "...",
      "poster_path": "/...jpg",
      "backdrop_path": "/...jpg",
      "score": 0.0123,
      "channels": {"synopsis": 0.83, "emotion": 0.18, "theme": 0.16},
      "genres": ["Action", "Thriller"],
      "archetype": "antihero",
      "protagonist_gender": "male",
      "vote_count": 14829,
      "vote_average": 7.4,
      "popularity": 35.6,
      "emotion_dna": {"cathartic": 0.35, "rage": 0.15, ...},
      "theme_dna": {"Action": 0.30, "revenge": 0.25, ...},
      "match_emotions": [
        {"tag": "cathartic", "query_weight": 0.22, "film_weight": 0.35, "contribution": 0.077}
      ],
      "match_themes": [...]
    }
  ],
  "search_time_ms": 50
}
```

---

## Use-Cases & Recipes

### A. Klassischer Frei-Text-Search

```python
import requests
r = requests.post("http://localhost:8000/api/search", json={
    "query": "düstere Rachefilme mit Happy End",
    "limit": 10
})
```

### B. „Wie dieser Film"

```python
r = requests.post("http://localhost:8000/api/search", json={
    "similar_to": 245891,        # John Wick TMDB-ID
    "limit": 10,
    "indie_mainstream": -0.3     # leicht Richtung Indie
})
```

### C. Mit User-Profil (Variant A — wir mitteln DNA der gelikten Filme)

```python
r = requests.post("http://localhost:8000/api/search", json={
    "query": "empfehl mir was passendes",
    "liked_tmdb_ids": [245891, 1813, 194],     # User-Historie
    "w_personal": 0.6,
    "limit": 10
})
```

### D. Mit externem Recommender-Modell (Variant B — Customer ML übergibt Scores)

```python
# Customer's CF/ML-Modell hat für User X folgende Score errechnet:
my_ml_scores = {245891: 0.95, 324552: 0.88, ...}    # tmdb_id → 0..1

r = requests.post("http://localhost:8000/api/search", json={
    "query": "spannende Action-Filme",
    "external_score_boost": my_ml_scores,
    "w_external": 1.5,            # 0=ignore, 1=equal, 2=external dominant
    "limit": 10
})
```

→ MindRead bleibt das **emotionale Retrieval-System**, der Customer behält seine ML-Pipeline.
   Ergebnis = beides kombiniert.

### E. Tenant-Deployment für Streaming-Anbieter

```bash
# Server-Start mit tenant-restriction
TENANT_PROVIDERS_ALLOWED="Magenta TV+,DAZN" \
  venv/bin/python3 -m uvicorn api_v3:app --host 0.0.0.0 --port 8000

# Effekt:
#  /api/providers   → zeigt nur Magenta TV+, DAZN
#  /api/search      → ohne explizit übergebene streaming_providers
#                     filtert automatisch auf Magenta TV+ ∪ DAZN
```

### F. Wheel-Adjustment ohne LLM-Call

Erste Suche normal (LLM-Call):
```json
{ "query": "Rachefilme" }
```
→ Response enthält `intent.emotion_sparse`, `intent.theme_sparse`.

Zweite Suche (Slider/Wheel-Anpassung), **kein LLM-Call**:
```json
{
  "query": "Rachefilme",
  "adjusted_emotions": {"rage": 0.4, "cathartic": 0.3, "grief": 0.3},
  "adjusted_themes":   {"revenge": 0.7, "Action": 0.3}
}
```

→ Backend benutzt direkt die übergebenen Sparse-Vektoren, kein OpenAI/LLM-Aufruf.
   Latenz ~30-50ms.

---

## Authentifizierung

Aktuell: **keine** (offene Demo-API).

Für Produktion:
- API-Key per Header: `Authorization: Bearer <key>`
- Konfiguration via `API_KEYS` env (Pflicht in v3.1)
- Rate-Limiting via Redis (geplant)

---

## Performance-Profile

| Modus | Latenz |
|:--|---:|
| Free-Text mit LLM | 2–4 s (OpenAI gpt-5.4-mini) |
| Free-Text + adjusted vectors (kein LLM) | 30–60 ms |
| similar_to | 30–60 ms |
| Mit external_score_boost | ~1.5 ms zusätzlich |
| Mit liked_tmdb_ids (≤50) | ~50 ms zusätzlich |

Alle Werte CPU-only. Mit GPU für Synopsis-Embedding wäre Free-Text-LLM-Pfad noch ca. 200 ms schneller.

---

## Versionierung

- API-Version im Response-Header: `X-MindRead-Version: 3.0.0`
- Breaking Changes nur bei Major-Bumps
- OpenAPI-Schema unter `/openapi.json`
