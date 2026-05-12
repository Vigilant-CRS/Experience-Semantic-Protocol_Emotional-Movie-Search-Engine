# Help Manuscript

Kurze Arbeitsanweisung für jeden Agenten (Claude, Codex, GPT, …) der an MindRead arbeitet.

## Pflichtlektüre vor Code

In dieser Reihenfolge:

1. `agent-memory/PROJECT_OVERVIEW.md` — was und für wen
2. `agent-memory/CURRENT_STATE.md` — aktueller Stand
3. `agent-memory/SESSION_HANDOFF.md` — was zuletzt passierte + was kommt
4. `agent-memory/DECISIONS.md` — Architektur-Entscheidungen mit Begründung
5. `agent-memory/FACTS.md` — Zahlen, Endpoints, Paths

Bei größeren architektonischen Eingriffen zusätzlich:

6. `agent-memory/THEORY_REGISTRY.md` — verwendete Theorien
7. `agent-memory/FORMAL_ASSUMPTIONS.md` — wovon das System ausgeht
8. `agent-memory/DERIVATIONS.md` — Formeln
9. `agent-memory/MODEL_LIMITS.md` — bekannte Schwächen
10. `agent-memory/THEORY_TO_CODE_MAP.md` — Theorie ↔ Code-Stellen
11. `agent-memory/VALIDATION_MATRIX.md` — was getestet ist
12. `agent-memory/DISPUTED_POINTS.md` — offene Designfragen
13. `agent-memory/HYPOTHESES.md` — was noch unbewiesen ist
14. `agent-memory/OPEN_THEORETICAL_GAPS.md` — Lücken
15. `agent-memory/EVIDENCE_LOG.md` — konkrete Belege

## Während Code-Arbeit

- **Strikt trennen** zwischen Fakt, Hypothese, Theorie, Heuristik, Entscheidung, Streitpunkt.
- **Nie Hypothese als Fakt schreiben.** Wenn du etwas behauptest, prüfe ob es in `FACTS.md` belegt ist.
- **Nie Heuristik als Theorie ausgeben.** Tone-Shift-Blend (60/40) ist Heuristik, nicht Theorie.

## Nach Code-Arbeit

Aktualisiere die betroffenen Memory-Dateien:

- Neue Architektur-Entscheidung → `DECISIONS.md` (mit Begründung)
- Neue Heuristik/Formel → `DERIVATIONS.md`
- Neue offene Frage → `DISPUTED_POINTS.md` oder `OPEN_THEORETICAL_GAPS.md`
- Test/Eval-Ergebnis → `EVIDENCE_LOG.md`
- Status-Update → `CURRENT_STATE.md` + `SESSION_HANDOFF.md`
- Neuer Code-Pfad einer existierenden Theorie → `THEORY_TO_CODE_MAP.md`
- Falsche Annahme entdeckt → `FORMAL_ASSUMPTIONS.md` updaten + Konsequenz vermerken

## Was du NIE tun darfst (ohne explizite User-Zustimmung)

1. **plot_themes/genres/settings/moods/pacing erweitern** — Index-Shift, Reindex zwingend
2. **synonyms.json reduzieren** — würde existierende Mappings brechen
3. **`OPENAI_API_KEY` oder andere Secrets in Code committen**
4. **`docker compose up` mit anderem Working-Dir starten** — relative Pfade brechen
5. **Qdrant-Collection droppen** ohne Backup
6. **Reindex mit `--recreate` starten** während Live-Queries laufen

## Befehle für häufige Tasks

### Status-Check (immer zuerst)

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
pgrep -af "extract_dna_v3|uvicorn api_v3"
wc -l data/movies_dna_v3.jsonl
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
```

### Eval

```bash
venv/bin/python3 scripts/eval_v3.py --json data/eval_results_$(date +%F).json
```

### API restart

```bash
pkill -TERM -f "uvicorn api_v3"; sleep 3
nohup env CUDA_VISIBLE_DEVICES= venv/bin/python3 -m uvicorn api_v3:app \
  --host 0.0.0.0 --port 8000 > data/api_v3.log 2>&1 & disown
```

### Qwen-Batch-Extract (lokal, GPU)

```bash
nohup env LOCAL_LLM_N_GPU_LAYERS=999 LOCAL_LLM_CTX=4096 \
  venv/bin/python3 scripts/extract_dna_v3.py \
  --source data/movies_top20k.json --local-llm --llm-size 4b \
  --out data/movies_dna_v3.jsonl >> data/dna_v3_overnight.log 2>&1 & disown
```

### OpenAI-Batch-Extract

```bash
nohup venv/bin/python3 scripts/extract_dna_v3.py \
  --source data/movies_top20k.json --workers 20 \
  --out data/movies_dna_v3.jsonl > data/dna_v3_openai.log 2>&1 & disown
```

## Kurz-Auftrag an dich (Pre-Prompt)

```text
Lies zuerst die Memory-Dateien laut Lesereihenfolge oben.
Arbeite den Code weiter im Sinne der dokumentierten Decisions.
Bevor du eine bestehende Decision änderst, dokumentiere die Begründung.
Schreibe Verifikation, Annahmen, Streitpunkte in die passenden Dateien zurück.
Wenn etwas nur plausibel ist, behandle es nicht als Fakt.
Wenn etwas theoretisch offen ist, markiere es als offen.
Halte Datums-Stempel in `CURRENT_STATE.md` und `SESSION_HANDOFF.md` aktuell.
```
