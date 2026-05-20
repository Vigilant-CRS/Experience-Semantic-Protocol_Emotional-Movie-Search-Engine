# Architecture

*Vigilant ESP — Experience Semantic Protocol (engine codename: MindRead V3).*

## High-Level Overview

```mermaid
flowchart LR
    subgraph Client["Client (Browser / Customer Backend)"]
        UI[Wheel UI / Slider Mix Bar]
        SDK[Customer Catalog Pipeline]
    end

    subgraph Engine["Vigilant ESP Container"]
        API[FastAPI / uvicorn :8000]
        E5[E5-large-v2 Embedder<br/>1024 dim · cached in RAM]
        LLM[LLM Provider<br/>OpenAI / Azure / Qwen GGUF]
        TX[TITLE_INDEX<br/>in-memory cache]
    end

    subgraph Storage["Qdrant Container :6333"]
        QD[(mindread_v3 collection<br/>15K-500K points)]
        V1[synopsis_dense 1024]
        V2[emotion_sparse 30]
        V3[theme_sparse 88]
        V4[subject_sparse 24]
        PL[payload: title, year, posters,<br/>setting, mood, pacing, content_features,<br/>color_palette, protagonist_age, ...]
    end

    subgraph External["External (per request)"]
        OAI[OpenAI API]
        TMDB[TMDB CDN<br/>image.tmdb.org]
    end

    UI -->|"POST /api/search"| API
    SDK -->|"POST /api/admin/films(/csv)"| API
    API -->|"chat completion"| LLM
    LLM -.->|"if OpenAI"| OAI
    API -->|"encode text → 1024 vec"| E5
    API -->|"resolve title"| TX
    API -->|"hybrid retrieve<br/>weighted RRF fusion"| QD
    QD --- V1 & V2 & V3 & V4 & PL
    UI -.->|"posters"| TMDB
```

## Request Path: Free-Text Query

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant LLM as LLM Provider
    participant Q as Qdrant
    participant E as E5 Embedder

    U->>API: POST /api/search<br/>{query, w_synopsis, w_emotion, w_theme, ...}
    API->>LLM: pass-1 prompt (canonical)
    LLM-->>API: intent JSON<br/>(similar_to_title, modifiers, avoid, age, ...)

    alt similar_to_title is set AND has "aber"/"but" modifier
        API->>Q: retrieve reference film payload
        Q-->>API: stored DNA<br/>(theme_dna, setting, mood, ...)
        API->>LLM: pass-2 anchored prompt<br/>(reference DNA injected)
        LLM-->>API: FINAL adjusted DNA<br/>(no further server blending)
    else pure "wie X" (no modifier)
        API->>Q: retrieve reference film
        Q-->>API: stored DNA (used directly)
    else topic query (no reference)
        Note over API: use pass-1 DNA directly
    end

    API->>E: encode translated_query → dense vec
    E-->>API: 1024-d vector
    API->>Q: weighted RRF fusion<br/>(synopsis_dense + emotion_sparse + theme_sparse + subject_sparse)
    Q-->>API: top-K candidates with channel ranks
    API->>API: post-fusion: avoid filters,<br/>color_palette boost, year filter,<br/>protagonist_age/gender filter,<br/>diversify (max 2 per franchise),<br/>pin reference if pure-title
    API-->>U: SearchResponse with match_reasons
```

## Hybrid Retrieval — Vector Layout

The collection has **four named vectors per film**, plus a JSON payload.
Each channel is queried independently and their rank lists are fused
with weighted RRF (Cormack 2009 extension):

```
score(d) = Σ_c w_c · 1 / (60 + rank_c(d))
```

| Channel | Dim | Source | Captures |
|---|---|---|---|
| `synopsis_dense` | 1024 | E5-large-v2 of overview text | Semantic synopsis similarity |
| `emotion_sparse` | 30 | Plutchik 8×3 + Wirkung 6 | Protagonist feelings + viewer impact (separately L1-normalised) |
| `theme_sparse` | 88 | plot_themes(35) + genres(18) + settings(15) + moods(12) + pacing(8) | Story DNA |
| `subject_sparse` | 24 | Subjects bucket (mafia, vampire, …) | Topical "what it's about" |

Plus payload-only buckets (additive, no reindex required to extend):
- `content_features` (10 advisories — firearms, drug_use, …) → hard `must_not`
- `color_palette` (6 — warm, neon_noir, …) → soft re-rank
- `protagonist_age` (6 — child, …, senior) → hard filter when no reference
- `protagonist_gender` (4) → hard filter when set
- `archetype`, `streaming_providers`, `year`, `vote_average`, …

## Ontology Layout (Schema v2, 2026-05)

```mermaid
flowchart TB
    subgraph SparseChannels[Sparse Vector Channels]
        direction LR
        E[emotion_sparse 30<br/>emotions 24 + wirkung 6<br/>each L1=1]
        T[theme_sparse 88<br/>plot_themes 35 + genres 18 +<br/>settings 15 + moods 12 + pacing 8]
        S[subject_sparse 24<br/>own channel with own slider]
    end
    subgraph DenseChannel[Dense Vector Channel]
        SY[synopsis_dense 1024<br/>E5-large-v2]
    end
    subgraph PayloadOnly[Payload-only Buckets<br/>additive · no reindex]
        CF[content_features 10]
        CP[color_palette 6]
        PA[protagonist_age 6]
        PG[protagonist_gender 4]
        AR[archetype 10]
    end
```

## Performance Numbers (measured 2026-05-15, n=10 per operation)

Hardware: P620 dev workstation, 15.255 indexed films, single-tenant, CPU-only.

| Operation | P50 | P95 | Notes |
|---|---|---|---|
| `POST /api/search` similar_to=tmdb_id | **147 ms** | **153 ms** | no LLM, just hybrid retrieve + diversify |
| `POST /api/search` topic query (1 LLM call) | **3.26 s** | **3.62 s** | OpenAI gpt-5.4-mini dominates (~2.5 s of total) |
| `POST /api/search` **cached intent (wheel-adjust)** | **259 ms** | **286 ms** | **client reuses prior intent — no LLM call** |
| `POST /api/search` tone-shift (Variant Z, 2 LLM calls) | **6.5 s** | **9.0 s** | pass-1 + anchored pass-2; outlier up to 18 s on OpenAI spikes |
| `POST /api/admin/films` 200 films (OpenAI) | 2-5 min | — | LLM-bound; serial; 0 errors typical |
| Qdrant search alone (any channel) | **<10 ms** | <20 ms | HNSW-indexed |
| E5 encode (single query) | **5-20 ms** | <30 ms | CPU; <2 ms on consumer GPU |

**Key insight for UI design:** after the first search-with-text, the client should retain `intent.emotion_sparse` + `intent.theme_sparse` and pass them back as `adjusted_emotions` + `adjusted_themes` for subsequent slider/wheel changes. That kills the LLM call and the search drops to **~250 ms — feels instant**.

P95 estimate for production catalog (50 K-500 K films):
- Latency unchanged for retrieval (HNSW is log-N)
- LLM-call latency depends on provider; same as demo
- Cold-start (container restart): ~30 s for E5 load + title-index build

## Deployment Topology

Recommended single-node deployment for ≤ 200 K films:

```
┌─────────────────────────────────────────────┐
│  Customer infrastructure (their datacenter) │
│                                              │
│  ┌──────────────┐         ┌──────────────┐  │
│  │ Vigilant ESP │◀───────▶│  Qdrant      │  │
│  │ container    │  HTTP   │  container   │  │
│  │ :8000        │         │  :6333       │  │
│  └──────┬───────┘         └──────┬───────┘  │
│         │                         │          │
│         ▼                         ▼          │
│   E5 weights                 qdrant_data     │
│   (cached vol)               (persistent vol)│
└─────────────────────────────────────────────┘
            │                       ▲
            │ HTTPS                 │ TVA / CSV
            ▼                       │ feed
   ┌────────────────┐      ┌─────────────────┐
   │  OpenAI API    │      │ Customer        │
   │  (or local LLM)│      │ catalog system  │
   └────────────────┘      └─────────────────┘
```

Multi-tenant: replicate the same stack per customer, route via reverse-proxy. Cluster-Qdrant + horizontal API scale is supported by upstream Qdrant but not currently bundled.
