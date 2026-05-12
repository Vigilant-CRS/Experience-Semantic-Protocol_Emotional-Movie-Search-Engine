# Current State — 2026-05-12

## ⚠️ Audit-Befund 2026-05-12 (CMR-002)

**Kritische Bugs entdeckt:**
- **F-001:** `avoid_content`-Filter ist seit Einführung **komplett tot** (must_not wird im HTTP-Body nicht serialisiert)
- **F-002:** `diversify()` verliert Items bei Franchise-Cap-Erreichen → liefert weniger als `limit`
- **F-005:** `llm_local.py` Prompt seit subjects-Erweiterung out-of-sync (4 fehlende Felder)
- **F-007:** 34 Tags (alle subjects + content_features) ohne DE-Translation
- **F-010:** Repo hat 0 Git-Commits — Audit-Trail fehlt
- **F-025:** docker-compose enthält nur qdrant, kein api/frontend

**Vollständiger Audit:** `agent-memory/CROSS_MODEL_REVIEW.md` (CMR-002).

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
