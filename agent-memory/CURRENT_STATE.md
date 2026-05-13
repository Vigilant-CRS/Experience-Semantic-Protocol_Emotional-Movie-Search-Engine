# Current State — 2026-05-13 (Block C abgeschlossen)

## 🎉 Schema v2 live, Korpus konsolidiert

**Korpus:**
- 15,255 Filme indexed (vorher 7,018)
- 15,232 mit Poster, 7,622 mit DE-Provider, 13,322 mit DE-Overview
- TITLE_INDEX: 18,918 keys (inkl. DE-Aliases)

**Schema v2 (config/engine_params.yaml schema.version=2):**
- emotion_sparse 30 dim — emotions(24) + wirkung(6) **separately L1-normalized** (F-016 ✓)
- theme_sparse 88 dim — themes(35) + genres(18) + settings(15) + moods(12) + pacing(8)
- subject_sparse 24 dim — **dedicated channel** mit eigenem w_subject Slider (F-017 ✓)
- synopsis_dense 1024 dim — E5-large-v2

**Empirische Qualitätsverbesserung:**
| Query | Pre-v2 | Post-v2 |
|---|---|---|
| Vampirfilme | Devil's Due / Satanic / Howl | **Dracula / Vampires / Nosferatu** ✓ |
| Mafia | One Hundred Steps / Infiltrator | One Hundred Steps / Criminal Activities / **The Godfather** |
| "Action ohne Schusswaffen" | John Wick / Furious 7 / Rage 🐛 | **Baki Hanma / Fast&Furious / Shadow Master** (martial arts!) |

**Cost dieses Schritts:** ~$3 (9172 Mini-Extract + 220 Full-Extract via OpenAI gpt-5.4-mini)

# Current State — 2026-05-12 (Block A-B abgeschlossen — vorherig)

## ✅ Repair-Pass abgeschlossen 2026-05-12 (CMR-002b)

**Sieben Audit-Fixes durchgeführt:**

| Bug | Status | Datei | Verifikation |
|---|---|---|---|
| F-001 must_not im Filter | ✅ FIXED | search_v3.py | 6 Unit-Tests + Qdrant E2E |
| F-002 diversify cap-pop | ✅ FIXED | search_v3.py | 3 Unit-Tests |
| F-015 L1-Renorm Tone-Shift | ✅ FIXED | api_v3.py | 3 Unit-Tests |
| F-007 DE-Translations 34 Tags | ✅ FIXED | translations_de.json | 162/162 abgedeckt |
| F-003 streaming_providers Index | ✅ FIXED | reindex_v3 + Live-Qdrant | 1914 Filme indexiert |
| F-004 content_features.* Indexe | ✅ FIXED | reindex_v3 + Live-Qdrant | 10 Float-Indexe |
| F-010 Git Initial Commit | ✅ FIXED | .gitignore + commit 38dbeb4 | git log zeigt commit |

**Verbleibende Findings aus CMR-002:** 18 offene (F-005, F-006, F-008..F-025) — siehe CROSS_MODEL_REVIEW.md.

**Eval nach Fixes:** 23-26/29 (LLM-Varianz, identisch zu vor-Audit).

**Vollständiger Audit-Trail:** `agent-memory/CROSS_MODEL_REVIEW.md` CMR-002 + CMR-002b.

# Current State — 2026-05-11 (vorherig)

## Was läuft

| Service | Status | Detail |
|---|---|---|
| Qdrant | ✅ up | docker `mindread_clean-qdrant-1`, port 6333, collection `mindread_v3` 7018 points |
| API uvicorn | ✅ up | port 8000, healthy |
| Qwen-Extract | ✅ running | PID läuft, ~50 Filme/h, ~73s/Film auf Quadro P620 |
| Frontend | ✅ accessible | served at `/` from `frontend/index.html` |

## Was wurde zuletzt geliefert (chronologisch)

| Datum | Lieferung |
|---|---|
| 2026-05-04 | GPU-Fix (Quadro P620 nach Reboot wieder sichtbar), CUDA-Toolkit installiert, llama-cpp mit CUDA gebaut |
| 2026-05-04 | Qwen 4B GGUF läuft auf GPU, ~3.7 GB VRAM, 73s/Film |
| 2026-05-04 | extract_dna_v3 um `--local-llm` und `--source` erweitert |
| 2026-05-04 | Overnight-Extract auf 14K (von movies_top20k.json) gestartet |
| 2026-05-06 | Eval-Suite um 16 Edge-Cases erweitert: gender flip, year filter, tone shift, avoid weapons |
| 2026-05-06 | LLM-Intent erweitert: `protagonist_gender`, `year_min`, `year_max`, `avoid_content` |
| 2026-05-06 | Tone-Shift „wie X aber Y" Prompt-Discipline: LLM extrahiert nur Modifier, nicht Reference-DNA |
| 2026-05-06 | `content_features` Bucket eingeführt (10 Tags, payload-only) |
| 2026-05-06 | numpy auf <2 gepinnt (sklearn-Kompatibilität nach CUDA-Build) |
| 2026-05-06 | `streaming_providers` in SearchResponse surfaced |
| 2026-05-06 | `subjects` Bucket eingeführt (24 Tags, an theme_sparse Layout angehängt) |
| 2026-05-08 | `/api/health` erweitert um `extracted_total` + `pending_reindex` |
| 2026-05-08 | Frontend health-stats zeigt indexed + pending, cache-busting |
| 2026-05-11 | LLM-Name aus UI-Header entfernt |
| 2026-05-11 | agent-memory neu strukturiert für MindRead |

## Was fehlt für B2B-Verkauf (Blocker)

1. **`POST /api/admin/films`** — Plug-and-Play Ingest-Endpoint. Ohne den kann der Käufer seinen Katalog nicht reinkippen.
2. **Docker-Compose-Bundle** für 1-Command-Deploy
3. **Auth + API-Keys** für Tenant-Isolation
4. **Korpus-Konsolidierung** — derzeit Mix aus alter DNA (7K) + neuer DNA (4K) + Lücke (10K)

## Aktuelle Eval-Resultate

- 26/29 Tests (≈ 90% pass) stabil. ±5% Varianz pro Run (LLM-Non-Determinismus bei T=0.1).
- Bekannte Fail: `edge_action_no_guns` — wegen leeren content_features bei alten 7K. Behebbar nur per Re-Extract.

## Kosten/Zeit für „Komplett-Korpus 21K mit voller Ontologie"

| Schritt | Kosten | Zeit |
|---|---|---|
| OpenAI Re-Extract der 10K fehlenden | $13.50 | 1h (workers=20) |
| OpenAI Re-Extract der alten 7K | $9.10 | 45min |
| Reindex E5 + Qdrant | $0 | 15min (GPU) / 75min (CPU) |
| TMDB-Enrichment (Poster/Provider/DE) | $0 | 80min |
| **Total** | **$22.60** | **~3-4h** |
