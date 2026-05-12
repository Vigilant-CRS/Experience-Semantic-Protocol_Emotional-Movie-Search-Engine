# Session Handoff — 2026-05-12

## CRITICAL — sofort vor allen anderen Arbeiten

**F-001 fixen** (10 min): `scripts/search_v3.py::_filter_to_dict` muss `must_not` und `should` serialisieren, sonst ist avoid_content-Filter komplett tot. Audit CMR-002 hat Bug empirisch verifiziert. Fix-Skizze siehe `CROSS_MODEL_REVIEW.md`.

**F-002 fixen** (15 min): `scripts/search_v3.py::diversify` Zeile 358-364 — Cap-Check vor pool.pop, sonst verschwinden Items.

**F-007 fixen** (30 min): `config/ontology_v3/translations_de.json` um 34 Tags ergänzen (10 content_features + 24 subjects).

**F-010 erfüllen** (5 min): Repo hat 0 Commits — `git add -A && git commit -m "initial: V3 baseline post-audit"`.

Nach diesen vier sind die kritischsten Audit-Findings entschärft.

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
