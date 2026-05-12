# Cross Model Review

Für Multi-Model-Kollaboration: Beobachtungen die ein anderer Agent (Claude, Codex, GPT) gemacht hat, wenn er den Code/Memory durchgegangen ist.

## Format

Jeder Eintrag:
- **Reviewer:** welches Modell, welches Datum
- **Kontext:** was wurde reviewed
- **Beobachtungen:** Findings (Fakt, Hypothese, Concern)
- **Empfehlung:** was tun
- **Status:** open / accepted / rejected / superseded

---

## CMR-001 — 2026-05-11 / Claude Opus 4.7 / Self-Review

**Kontext:** Vollständige Projekt-Bewertung nach Subjects-Bucket-Erweiterung.

**Beobachtungen:**
- Search-Engine substanziell besser als vor 5 Tagen
- B2B-Produkt-Infrastruktur fehlt vollständig
- Korpus inkonsistent (7K alt + 4K Qwen + 10K fehlend)
- LLM-Local-Pfad nicht synchron
- Eval-Tests wurden mehrfach erweitert um Engine-Output zu fitten

**Status:** superseded by CMR-002

---

## CMR-002b — 2026-05-12 / Claude Opus 4.7 / Fix-Verifikation

**Kontext:** Repair-Pass nach Audit CMR-002. Re-verifikation jedes Findings, dann sequenzieller Fix mit Unit-Tests + E2E-Verifikation.

**Status der CMR-002 Findings:**

| # | Finding | Status nach 2026-05-12 |
|---|---|---|
| F-001 | `_filter_to_dict` must_not | ✅ **FIXED** — `_condition_to_dict` Helper + must/must_not/should-Serialisierung. 6 Unit-Tests pass. Empirisch via Qdrant verifiziert. |
| F-002 | diversify pop-skip | ✅ **FIXED** — Cap-Check VOR pool.pop. 3 Unit-Tests pass. limit=10 liefert jetzt soviel wie der diverse Pool erlaubt. |
| F-015 | Tone-Shift L1 | ✅ **FIXED** — `normalize_l1` nach Blend in api_v3. 3 Unit-Tests pass (alle L1=1.0). |
| F-007 | DE-Translations | ✅ **FIXED** — 34 Tags ergänzt, jetzt 162/162. UI-Test bestätigt: mafia→Mafia, firearms→Schusswaffen, espionage→Spionage. |
| F-003 | streaming_providers Payload-Index | ✅ **FIXED** — Code in reindex_v3 + Live-Qdrant-Patch (1914 points indexiert). |
| F-004 | content_features.* Payload-Indexe | ✅ **FIXED** — 10 Float-Indexe für alle content_features Sub-Keys angelegt (Code + Live). |
| F-010 | 0 Git-Commits | ✅ **FIXED** — `.gitignore` mit Secrets-Schutz + Initial-Commit `38dbeb4`. |

**Eval nach Fix:** 23-26/29 pass (LLM-Varianz). Vor Audit 25-26/29. → Fixes haben nichts gebrochen.

**Verbleibende offene Findings aus CMR-002** (Stand 2026-05-12 Block-A-Pass):
- ✅ F-005: llm_local.py Prompt synchronisiert via `build_query_user_prompt` (Block A)
- ✅ F-006: drei `llm_query_to_dna` durch einen canonical Builder ersetzt (Block A)
- ✅ F-008: eval_v3_expanded.py mit Deprecation-Header (Block A)
- ✅ F-009: requirements.txt von 31 → 18 Pakete, 10 Phantom-Deps raus + llama-cpp-python rein (Block A)
- F-011: 580 Filme ohne genres im Payload (ETL-Problem)
- F-012: Magic Numbers ohne zentrale Konstante
- F-013: indie-Slider versteckte va≥7 Klausel
- F-014: Boost auf RRF-Score nicht skaleninvariant
- F-016: emotion+wirkung joint-L1
- F-017: subjects 1/5 Theme-Beitrag
- F-018: Synopsis 500-char Truncate
- F-019: _find_film_by_title brittle
- F-020: TITLE_INDEX stale nach Reindex
- F-021: CORS *
- F-022: extracted_total duplicates
- F-023: Übersetzung mixed
- F-024: Qwen3.5 Naming
- F-025: docker-compose ohne api/frontend

**Empfohlene nächste Iteration:**
1. F-006 + F-005 — Prompt-Single-Source-of-Truth (verhindert künftige Drift)
2. F-025 — Docker-Bundle mit api+frontend (B2B-Blocker)
3. F-009 — Phantom-Deps entfernen (saubere Vendor-Review)

**Status:** Phase 1 abgeschlossen. Engine-Konsistenz substanziell verbessert.

---

## CMR-002 — 2026-05-12 / Claude Opus 4.7 / Harter Senior-Audit

**Kontext:** Vollständiges, systematisches dateiübergreifendes Audit über api_v3.py, search_v3.py, extract_dna_v3.py, reindex_v3.py, llm_local.py, frontend/index.html, alle 12 Ontology-JSONs, agent-memory, docker-compose, requirements, git-state.

**Kritische Findings (verifiziert):**

| # | Finding | Schweregrad | Verifikation |
|---|---|---|---|
| F-001 | `_filter_to_dict` droppt `must_not` → avoid_content erreicht Qdrant NIE | **kritisch** | verifiziert via Code + HTTP-Test |
| F-002 | `diversify()` pop-aber-skip-continue: items verschwinden bei Cap-Erreichen | hoch | verifiziert via Code-Read |
| F-005 | `llm_local.py` Prompt out-of-sync (kein subjects/content/gender/year) | kritisch (latent) | verifiziert |
| F-006 | 3 divergierte `llm_query_to_dna` Implementierungen | hoch | verifiziert |
| F-007 | 34 Tags ohne DE-Translation (alle subjects + alle content_features) | hoch | verifiziert |
| F-010 | Repo hat 0 Git-Commits | kritisch (Audit-Trail) | verifiziert |
| F-025 | docker-compose enthält nur qdrant, kein api/frontend | kritisch (B2B-Anspruch) | verifiziert |

**Hohe Findings:**
| # | Finding | Verifikation |
|---|---|---|
| F-003 | streaming_providers ohne Payload-Index → linearer Scan | verifiziert |
| F-004 | content_features.* ohne Payload-Index | verifiziert |
| F-011 | 580 Filme ohne genres im Payload | verifiziert |

**Mittlere Findings:**
- F-008: eval_v3_expanded.py parallel zu eval_v3.py → Dead-Code-Verdacht
- F-009: requirements.txt enthält `mistralai`, `streamlit`, `redis` ohne Imports → Phantom-Deps
- F-012: Magic Numbers in scoring (0.01, 0.02, 0.5, 0.4, 0.7) ohne zentrale Konstante
- F-013: indie_mainstream-Slider hat versteckte `vote_average >= 7.0` Klausel
- F-014: Popularity/Avoid-Penalty addiert absolute Werte auf RRF — bricht Skaleninvarianz
- F-015: Tone-Shift-Blend bricht L1-Norm (kein Re-Normalize nach 60/40 Mix)
- F-016: emotion+wirkung joint-L1-normalisiert — zwei verschiedene Achsen vermischt
- F-017: Subjects mit nur 1/5 Theme-Beitrag — strukturell schwach
- F-018: Synopsis truncated 500 chars in Payload, Embedding aus voller — Diskrepanz
- F-020: TITLE_INDEX wird einmal beim Startup gebaut, stale nach Reindex
- F-022: `extracted_total` zählt JSONL-Zeilen, nicht unique tmdb_ids — Duplikate verzerren

**Konsistenz-Widersprüche dokumentiert:**
- DECISIONS.md D-005 sagt „content_features Hard-Filter funktioniert graceful" — F-001 macht das zur Lüge
- DECISIONS.md D-008 + HYPOTHESES.md H-002 widersprechen sich (60/40 ist „getuned" vs „nicht bewiesen")
- THEORY_REGISTRY.md T-004 bezeichnet unsere weighted-RRF als „standard_method (RRF)" — ist Eigen-Erweiterung
- search_v3.py main() Default `0.5/0.3/0.2` ≠ api_v3.py Default `0.35/0.35/0.30`

**Theorie-Kritik:**
- Weighted RRF ist Eigen-Erweiterung, nicht klassisches RRF (Cormack 2009 wichtet NICHT)
- Bucket-Asymmetrie joint vs separat L1 ohne Begründung
- Append-Only-Theorem (DERIVATIONS D-011) ist mathematisch korrekt — gute Theorie

**Empfehlungen (Reihenfolge):**

1. **SOFORT** F-001 fixen — `_filter_to_dict` muss must_not + should serialisieren. 10 min, kritisch.
2. **SOFORT** F-010 — git init commit setzen
3. **HEUTE** F-002 Diversify-Bug fixen
4. **HEUTE** F-007 translations_de.json um 34 Tags ergänzen
5. **DIESE WOCHE** F-005 + F-006 — drei LLM-Prompt-Versionen konsolidieren
6. **DIESE WOCHE** F-025 — Docker-Bundle mit api+frontend
7. **DIESE WOCHE** F-003 + F-004 — Payload-Indexe ergänzen
8. **DANN** F-015 L1-Renorm, F-012 zentrale Score-Konstanten, F-009 Phantom-Deps weg

**Verbleibende Theorie-Fragen (in OPEN_THEORETICAL_GAPS):**
- Optimaler Tone-Shift-Blend (60/40 ist Heuristik ohne Evidenz)
- Subject-Channel-Gewichtung (1/5 zu schwach?)
- emotion+wirkung Joint-L1 zu reformieren?
- Score-Skala-Invarianz vs absolute Boost-Werte

**Gesamteinschätzung:** „fragil mit kritischen Lecks". Engine-Konzept solide, drei kritische Konsistenz-Versagen. Bei B2B-Demo darf F-001 nicht verkauft werden, weil die avoid-content-Story komplett unwahr ist.

**Status:** open

---

## CMR-003 — Template für nächsten Eintrag

**Reviewer:** [Modell/Datum]
**Kontext:** [was reviewed]
**Beobachtungen:** [Beobachtungen]
**Empfehlungen:** [konkret]
**Status:** [open|accepted|rejected|superseded]
