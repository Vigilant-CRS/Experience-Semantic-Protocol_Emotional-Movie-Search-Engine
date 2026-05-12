# Session Handoff — 2026-05-12 (Repair-Pass)

## ✅ Audit-Fixes durch — Block A komplett (commit 38dbeb4 + Block A)

**Initial Commit 38dbeb4** mit F-001, F-002, F-015, F-007, F-003, F-004, F-010.

**Block A (2026-05-12 später):**
- ✅ F-005 + F-006: `build_query_user_prompt` + `parse_query_dna` in extract_dna_v3.py als Single-Source-of-Truth. api_v3, llm_local und search_v3 CLI nutzen jetzt alle dieselbe Logik.
- ✅ F-008: eval_v3_expanded.py mit Deprecation-Header (41 Test-Ideen als Future-Merge-Pool erhalten)
- ✅ F-009: requirements.txt entschlackt von 31 → 18 Pakete. Phantom-Deps weg: mistralai, streamlit, redis, aiohttp, plotly, aiofiles, tenacity, pandas, python-dotenv, pyyaml, python-multipart, httpx, pytest-asyncio, ipython. llama-cpp-python ergänzt (war nicht deklariert).

Details in `CROSS_MODEL_REVIEW.md` CMR-002b.

## Was als nächstes ansteht

**Block A — verbliebene Konsistenz-Findings (✅ COMPLETE)**

**Block B — B2B-Produkt-Infrastruktur (2-3 Tage):**
- F-025: docker-compose mit api+frontend (1-Command-Deploy)
- `POST /api/admin/films` Plug-and-Play Ingest-Endpoint
- Auth + API-Keys für Tenant-Isolation

**Block C — Korpus konsolidieren ($22, 4h):**
- OpenAI-Re-Extract der 10K fehlenden Filme
- OpenAI-Re-Extract der alten 7K für volle Ontologie-Konsistenz
- Reindex mit den neuen Payload-Indexes (F-003+F-004 schon in setup_collection)
- TMDB-Enrichment-Chain

**Block D — Theorie-Verbesserungen (low priority):**
- F-016: emotion/wirkung separate L1
- F-017: Subject-Channel-Gewichtung
- F-014: Boost-Skala-Invarianz
- F-013: Indie-Slider va≥7-Asymmetrie
- F-018: Synopsis 500-char Truncate
- F-022: Dedupe JSONL für extracted_total

# Session Handoff — 2026-05-12 (vorherig — pre-Repair)

# Session Handoff — 2026-05-11 (vorherig)

## Was zuletzt passiert ist

**Letzte Session (heute):**
- agent-memory komplett neu strukturiert für MindRead (vorher Geolocation-Template)
- LLM-Modell-Name aus UI-Header entfernt (User-Request)
- Project-Re-Assessment: ehrliche Bewertung dass B2B-Infrastruktur (Plug-and-Play Ingest, Docker-Bundle, Auth) fehlt

**Vorherige Sessions:**
- 2026-05-08: `/api/health` um `extracted_total` + `pending_reindex` erweitert, UI zeigt Live-Counter beim Reload
- 2026-05-06 II: `subjects`-Bucket (24 Tags) in theme_sparse Layout (Indices 88-111) appended
- 2026-05-06: LLM-Intent um protagonist_gender, year_min/max, avoid_content erweitert; tone-shift Prompt-Discipline; content_features Bucket (10 Tags, payload-only)
- 2026-05-04 ff.: GPU+Qwen lokaler Batch-Extract läuft

## Was als nächstes ansteht (Prioritäts-Reihenfolge)

### Block A — Korpus konsolidieren (4h, $22)

1. Qwen-Extract stoppen
2. `extract_dna_v3.py` für die fehlenden ~10K Filme via OpenAI starten (`--workers 20`, ca. 1h)
3. Re-Extract der alten 7K via OpenAI für volle Ontologie-Konsistenz (~45min)
4. Reindex via `reindex_v3.py --recreate` (GPU testen, sonst CPU ~75min)
5. TMDB-Enrichment-Chain (Poster, Provider DE, Titel/Overviews DE) ~80min
6. Eval-Suite ausführen, Pass-Rate dokumentieren

**Effekt:** Konsistentes 21K-Korpus mit voller Ontologie. „Vampirfilme" und „John Wick ohne Schusswaffen" funktionieren dann sauber.

### Block B — B2B-Produkt-Infrastruktur (2-3 Tage)

7. `POST /api/admin/films` — akzeptiert CSV oder JSON-Liste, triggert DNA-Extract + Reindex automatisch
8. Docker-Compose-Bundle: api + qdrant + frontend in einem `docker compose up`
9. Auth-Layer: API-Keys per Tenant, JWT-Middleware

### Block C — Polish & Eval

10. `llm_local.py` mit neuer Ontologie/Prompt synchronisieren (Subjects/Content/Gender/Year)
11. Eval-Tests in Eigenschafts-Tests umbauen (nicht mehr „enthält Film X" sondern „enthält Filme mit Tag Y > Z")
12. Mobile-Layout
13. Onboarding-Tour

## Was JETZT läuft (Background)

| Prozess | PID-Anker | Was tut es |
|---|---|---|
| qdrant docker | container `mindread_clean-qdrant-1` | Vector DB |
| uvicorn api_v3 | latest start log in `data/api_v3.log` | API server |
| extract_dna_v3 Qwen | latest log in `data/dna_v3_overnight.log` | Batch-Extract, ~50 Filme/h |

## Häufige Befehle

```bash
# Status
wc -l data/movies_dna_v3.jsonl
curl -s http://localhost:8000/api/health | python3 -m json.tool
pgrep -af "extract_dna_v3|uvicorn api_v3"
nvidia-smi

# Eval
venv/bin/python3 scripts/eval_v3.py --json data/eval_results_latest.json

# API restart
pkill -TERM -f "uvicorn api_v3"; sleep 3
nohup env CUDA_VISIBLE_DEVICES= venv/bin/python3 -m uvicorn api_v3:app \
  --host 0.0.0.0 --port 8000 > data/api_v3.log 2>&1 & disown

# Qwen extract restart
nohup env LOCAL_LLM_N_GPU_LAYERS=999 LOCAL_LLM_CTX=4096 \
  venv/bin/python3 scripts/extract_dna_v3.py \
  --source data/movies_top20k.json \
  --local-llm --llm-size 4b \
  --out data/movies_dna_v3.jsonl \
  >> data/dna_v3_overnight.log 2>&1 & disown
```

## Was NICHT mehr tun

- ❌ plot_themes/genres/settings/moods/pacing nicht in der Mitte erweitern (D-004)
- ❌ Neuen Bucket vor `subjects` einfügen (würde Layout brechen)
- ❌ LLM-Local-Pfad ohne Sync mit api_v3 Prompt aktivieren
- ❌ Ontologie-Tag löschen ohne Re-Extract (würde stored Vektoren auf falsche Tags zeigen lassen)
