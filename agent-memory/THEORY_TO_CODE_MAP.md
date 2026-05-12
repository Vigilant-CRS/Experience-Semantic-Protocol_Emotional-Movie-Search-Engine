# Theory to Code Map

Welche Theorie/Entscheidung wird wo im Code umgesetzt. Bei Code-Änderungen prüfen ob Theorie noch passt.

| Theorie/Decision | Code-Stelle | Zeile/Funktion |
|---|---|---|
| T-001 E5 Dense Embedding | `scripts/search_v3.py::encode_query_text` | `SentenceTransformer.encode(..., normalize_embeddings=True)` |
| T-002 Sparse L1-Normalisierung | `scripts/extract_dna_v3.py::normalize_l1` | und `normalize_dna` |
| T-003 Plutchik Buckets | `config/ontology_v3/emotions.json` + `wirkung.json` | 24+6 tags |
| T-004 RRF Fusion | `scripts/search_v3.py::manual_weighted_fusion` | gewichtete 1/(60+rank)-Summation |
| T-005 Tone-Shift-Blend | `api_v3.py::search()` ~line 632-655 | 60/40 ref/modifier mixing |
| T-006 Synonym-Decay 0.7 | `scripts/extract_dna_v3.py::filter_to_canonical` | `* 0.7` factor |
| T-007 Append-Only Layout | `scripts/search_v3.py::load_indices` + `scripts/reindex_v3.py::load_ontology_indices` | Reihenfolge: th+gn+settings+moods+pacing+subjects |
| T-008 Asymmetrische Avoid | `api_v3.py::search()` + `scripts/search_v3.py::manual_weighted_fusion` | 3 Mechanismen (Score-Penalty, must_not, must) |
| T-009 Qwen 4B Q5_K_M | `scripts/llm_local.py::get_llm` | model_path=Q5_K_M GGUF |
| T-010 Software-License-Modell | `agent-memory/business_model.md` | dokumentiert, keine SaaS-Komponenten |
| D-001 Hybrid 3-Vektor | `api_v3.py::search()` baut alle 3 channels | synopsis_vec + emotion_sparse + theme_sparse |
| D-002 35 plot_themes | `config/ontology_v3/plot_themes.json` | tags array |
| D-003 EN-only E5 | `api_v3.py::llm_query_to_dna` extrahiert `translated_query` | dann encode_query_text(translated_query) |
| D-004 Append-Only | siehe T-007 | — |
| D-005 Content-Features Payload-Only | `api_v3.py::search()` + `reindex_v3.py::points payload` | content_features in payload, must_not filter |
| D-006 Subjects in theme_sparse | `scripts/search_v3.py::load_indices` + `reindex_v3.py::load_ontology_indices` | subjects at end of concatenation |
| D-007 LLM-Intent-zentral | `api_v3.py::llm_query_to_dna` | one call, all extraction |
| D-008 60/40 Blend | siehe T-005 | hard-coded constants |
| D-009 Qwen Batch | `scripts/extract_dna_v3.py` + `scripts/llm_local.py` | --local-llm flag wired through |
| D-010 Software-Lizenz | architectural absence: no /admin/* SaaS endpoints | — |
| D-011 Avoid Asymmetrie | siehe T-008 | — |
| D-012 gpt-5-mini Default | `api_v3.py` env `OPENAI_MODEL_DNA` default | OPENAI_MODEL env var |

## Code → Theorie (Reverse-Lookup)

| Datei | Welche Theorien anwesend |
|---|---|
| `api_v3.py` | T-005, T-008, D-001, D-003, D-005, D-007, D-008, D-011, D-012 |
| `scripts/extract_dna_v3.py` | T-002, T-006, T-009, D-009 |
| `scripts/search_v3.py` | T-001, T-002, T-004, T-007, T-008, D-006 |
| `scripts/reindex_v3.py` | T-002, T-007, D-005, D-006 |
| `scripts/llm_local.py` | T-009, D-009 (Status: nicht aktuell mit api_v3-Prompts!) |
| `frontend/index.html` | D-001 (3-Slider-UI), Wheel-Anpassung |
| `config/ontology_v3/*.json` | T-003 (Plutchik), D-002 (35), D-005, D-006 |

## Wichtige Sync-Bedingungen

**Zwei Stellen MÜSSEN synchron sein:**
1. `scripts/search_v3.py::load_indices` — definiert wie Query-Vektoren gebaut werden
2. `scripts/reindex_v3.py::load_ontology_indices` — definiert wie Storage-Vektoren gebaut werden

Wenn die divergieren, matching ist kaputt. **Test:** `python3 -c "from scripts.search_v3 import load_indices; from scripts.reindex_v3 import load_ontology_indices; a=load_indices(); b=load_ontology_indices(); assert a == b, 'INDEX DRIFT'"`

**Code-Drift-Risiko:** `scripts/llm_local.py` enthält eine Kopie des LLM-Prompts. Wenn `api_v3.py::llm_query_to_dna`-Prompt aktualisiert wird, `llm_local.py::llm_query_to_dna_local` mit-updaten. Aktuell out-of-sync (subjects, content_features, gender, year fehlen).
