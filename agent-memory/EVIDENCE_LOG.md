# Evidence Log

Konkrete Belege, Eval-Ergebnisse, Benchmarks. Wenn etwas behauptet wird in DECISIONS/HYPOTHESES, sollte hier die Evidenz stehen.

## E-001 GPU-Speed Qwen 4B Q5_K_M auf Quadro P620

**Setup:** Quadro P620, 4034 MiB VRAM, alle 24 Layer auf CUDA.

**Messung (2026-05-04 pilot):**
- Short call (200 tokens prompt + 20 output): 2.17s
- Longer call (200 prompt + 200 output): 6.49s
- Full DNA extract (2400 system prompt + 200 user + 600 output): 42-57s

**Konsequenz:** Lokales Qwen ist für Batch praktikabel (~50 Filme/h), für Runtime unbrauchbar.

## E-002 Pilot-Test John Wick → DNA via Qwen 4B

**Input:** „John Wick" 2014, ex-hitman seeking revenge, etc.

**Output:**
```
emotion: rage(0.15), grief(0.125), anticipation(0.1), dread(0.075)
theme:   revenge(0.25), grief_and_loss(0.1), underdog_triumph(0.075), betrayal(0.075)
archetype: antihero
mood: dark(0.5), gritty(0.3), noir(0.2)
```

Exact match zum Few-Shot-Beispiel im System-Prompt. **Beleg:** Qwen 4B kann das Pattern reproduzieren.

## E-003 Eval-Suite Baseline (vor B-Phase Fixes)

**Datum:** 2026-05-06 erste Eval-Erweiterung.
**Pass:** 19/29 (66%)

**Hauptfailures:**
- edge_action_no_guns (kein content_features → John Wick top)
- edge_john_wick_female_lead (kein protagonist_gender im LLM-Output)
- edge_amelie_more_action (kein Tone-Shift Disziplin)
- edge_provider_netflix (false positive — providers waren da, nur nicht in Response)
- 90s_romcom (kein year_min/max im LLM-Output)

## E-004 Eval-Suite Nach LLM-Schema-Erweiterung

**Datum:** 2026-05-06 nach Fix von gender, year_min/max, tone-shift.
**Pass:** 26/29 (90%)

**Wins:**
- edge_john_wick_female_lead: 2/2 hits
- edge_90s_romcom: 4/2 hits (year filter wirkt)
- edge_provider_netflix: passt mit korrektem Provider-Check

**Verbleibende Fails (semantisch valide, aber außerhalb erwarteter Liste):**
- edge_amelie_more_action
- edge_action_no_guns (echte Ontologie-Lücke)
- freetext_family (Test-Liste zu eng)

## E-005 Eval-Suite Nach Subjects-Bucket

**Datum:** 2026-05-06 nach Subjects-Bucket-Hinzufügung.
**Pass:** 25/29 (86%) bis 26/29 (90%) — Variance.

**Wins:**
- Subject-Queries empirisch besser: Mafia 5/5, Espionage 3/5 (vs 1/5 vorher).

**Variance:** 4 Eval-Runs an einem Tag, Passes 23/25/25/26 — bestätigt LLM-Non-Determinismus.

## E-006 Empirische Subject-Coverage-Tests

**Datum:** 2026-05-06.
**Queries:** „Vampirfilme", „Mafiafilme", „Spionagefilme", „Kampfsportfilme", „Filme im Knast"

**Ergebnis (Top-3 Filme, Subject vom LLM extrahiert):**

| Query | Subject | Top-3 | Quality |
|---|---|---|---|
| Vampir | vampire ✓ | Devil's Due, Satanic, Howl | 0/3 (alte Filme ohne subject-tag) |
| Mafia | mafia ✓ | The Family, Suburra, Mafia Kills Only in Summer | 5/5 (E5 trägt) |
| Spionage | espionage ✓ | Spectre, North by Northwest, Basic Instinct | 2/3 |
| Kampfsport | martial_arts ✓ | Over the Top, Man of Tai Chi, Tarzan | 1/3 |
| Knast | prison_life ✓ | Cold Comes the Night, 13, Tie Me Up | 0/3 (alte Filme ohne tag) |

**Erkenntnis:** Subject-Extraktion klappt 100% korrekt aus Query. Ergebnis-Qualität nur dann hoch wenn (a) E5 trägt das Signal ODER (b) Filme haben das Subject-Tag gespeichert.

## E-007 Qwen-Output mit neuer Ontologie (Sample)

**Datum:** 2026-05-06.

```json
"Fled":     {"subjects": {"mafia":0.375, "prison_life":0.375, "espionage":0.25},
             "content_features": {"firearms":0.47, "vehicular_combat":0.24, ...}}
"Family Plot": {"subjects": {"serial_killer":1.0}}
"Greatest Story Ever Told": {"subjects": {"historical_event":0.6, "biopic":0.4}}
```

**Beleg:** Qwen produziert vernünftige Subject-Tags, weighted, multi-tag wo angebracht.

## E-008 Korpus-Stand 2026-05-11

```
JSONL-Zeilen:        11,085
Qdrant points:        7,018
Pending Reindex:      4,067
Source-Korpus:       21,418
Extract-Errors:           4 (über >11K Extracts, < 0.04% Failure-Rate)
```

## E-010 (2026-05-12) Audit-Beweis F-001 `_filter_to_dict` droppt must_not

**Test:**
```python
from scripts.search_v3 import _filter_to_dict
from qdrant_client.models import Filter, FieldCondition, Range
f = Filter(
    must=[FieldCondition(key='year', range=Range(gte=2000))],
    must_not=[FieldCondition(key='content_features.firearms', range=Range(gt=0))]
)
print(_filter_to_dict(f))
```

**Output:**
```
{'must': [{'key': 'year', 'range': {'gte': 2000.0}}]}
```

→ must_not fehlt komplett. Bug **VERIFIZIERT**.

## E-011 (2026-05-12) Korpus-Stand 0 Filme mit content_features.firearms im Payload

Direct Qdrant scroll mit Filter `content_features.firearms range:gt:0` → 0 Filme.

Konsequenz: Selbst nach F-001-Fix würde der Filter aktuell nichts ausschließen, weil alte 7K Filme das Feld nicht haben (Ontologie wurde erst nach Initial-Extract eingeführt).

## E-012 (2026-05-12) Payload-Indexes vorhanden

Qdrant payload_schema-Endpoint zeigt Indexe für: vote_average, vote_count, genres, archetype, tmdb_id, year, popularity, protagonist_gender, runtime.

**Fehlend:** streaming_providers, content_features.* (jeder Sub-Key müsste separat indexiert sein).

## E-013 (2026-05-12) Translations DE Coverage

162 canonical Tags total. translations_de.json hat 128 Einträge. → 34 Tags ohne DE-Label (alle 10 content_features + alle 24 subjects).

## E-014 (2026-05-12) Phantom-Dependencies

`requirements.txt` listet:
- `mistralai==0.4.2` — grep finds 0 imports
- `streamlit==1.35.0` — grep finds 0 imports
- `redis==5.0.1` — grep finds 0 active uses (Redis docker-compose ist auskommentiert)

→ Drei Dependencies können entfernt werden.

## E-016 (2026-05-12) Repair-Pass abgeschlossen

**Commit `38dbeb4` enthält 7 Fixes** (siehe CROSS_MODEL_REVIEW CMR-002b):

| Fix | Test | Resultat |
|---|---|---|
| F-001 _filter_to_dict | 6 Unit-Tests | alle pass |
| F-002 diversify | 3 Unit-Tests | alle pass; 8 JW + 2 andere, cap=2 → 4 Filme zurück |
| F-015 L1-Renorm | 3 Unit-Tests | L1=1.0 in allen 3 Cases (empty/disjoint/overlap modifier) |
| F-007 Translations | Coverage-Check | 162/162 Tags abgedeckt |
| F-003/F-004 Indexe | Qdrant payload_schema | 20 Indexe gesamt (vorher 9) |
| F-010 Git Commit | git log | commit 38dbeb4 root-commit |

**Live Qdrant patched:**
- streaming_providers: keyword (1914 points indexed)
- content_features.firearms..drug_use: float (0 points — alte Filme haben Feld nicht)

**Eval-Suite nach Fixes:** 23-26/29 (LLM-Varianz, identisch zu pre-audit).

## E-015 (2026-05-12) Git-Status

`git log` → „Branch hat noch keine Commits". Alle Python-Files sind untracked. Kein Audit-Trail.

## E-009 Eval-Suite Konsistenz-Run 2026-05-11

**Pass:** 26/29 (90%)
**Avg server time:** 2388ms
**Top-Failures:** 
- freetext_family (semantisch ok aber außerhalb Liste): Parental Guidance, Mother's Day, That's Life
- edge_action_no_guns: John Wick (echter Ontologie-Bug)
- edge_amelie_more_action: variability
- freetext_mindbending: variability
