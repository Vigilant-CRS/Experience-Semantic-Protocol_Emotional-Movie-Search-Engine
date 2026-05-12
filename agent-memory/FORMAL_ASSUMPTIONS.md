# Formal Assumptions

Annahmen, unter denen das System mathematisch oder semantisch funktioniert. Wenn eine davon nicht gilt, ist das Verhalten undefiniert.

## A-001 LLM-Output ist syntaktisch valides JSON

**Annahme:** `response_format={"type":"json_object"}` bei OpenAI / strict JSON-Output bei Qwen liefert immer parsbares JSON.

**Verletzung:** Falls JSON-Parse fehlschlägt, fängt `call_openai`/`call_local` mit `json.JSONDecodeError` ab, retried bis zu N mal, danach wirft Exception. Eval-Suite würde Film als Error zählen.

**Praktische Robustheit:** Bisher 0 Errors auf 11K Extracts via Qwen + 7K via gpt-5-mini.

## A-002 LLM verwendet ausschließlich kanonische Tags

**Annahme:** LLM hält sich an die im System-Prompt aufgelisteten Tag-Namen.

**Verletzung:** Wird durch `filter_to_canonical` abgefangen: nicht-kanonische Tags werden via `synonyms.json` mit Decay 0.7 gemappt oder verworfen. Falls weder kanonisch noch synonym → silent drop.

**Konsequenz:** Schwacher LLM-Output (viele non-canonical Tags) reduziert DNA-Stärke, bricht das System aber nicht.

## A-003 Theme-Sparse Bucket-Indices sind stabil (Append-Only-Disziplin)

**Annahme:** Die Reihenfolge `plot_themes + genres + settings + moods + pacing + subjects` ist permanent festgelegt. Neue Buckets werden nur am Ende angehängt.

**Verletzung:** Indices verschieben sich, gespeicherte Sparse-Vektoren zeigen auf falsche Tags. Symptom: völlig falsche Suchergebnisse, kein Crash.

**Schutz:** `search_v3.py::load_indices` und `reindex_v3.py::load_ontology_indices` haben Kommentare die das festhalten. Verletzung erfordert vollständigen Re-Index.

## A-004 E5-Embeddings sind L2-normalisiert

**Annahme:** `SentenceTransformer.encode(..., normalize_embeddings=True)` liefert Unit-Vektoren. Dann ist cosine ≡ dot product.

**Verletzung:** Wenn nicht normalisiert, würden längere Filme höhere Cosine-Scores bekommen → Bias.

**Schutz:** `encode_query_text` ruft mit `normalize_embeddings=True` auf.

## A-005 Qdrant kann Sparse-Vektoren beliebig dimensional speichern

**Annahme:** Qdrant SparseVector hat keine fixe Dimension — speichert nur (indices, values) pairs.

**Verletzung:** Wäre eine Qdrant-Versionsregression. Aktuelle Version (1.14) bestätigt: keine dimension-bound.

## A-006 Translation-Step vor E5 ist semantik-erhaltend

**Annahme:** LLM-Übersetzung Deutsch→Englisch erhält den emotionalen/thematischen Gehalt der Query, sodass E5-Embedding semantisch korrekt ist.

**Verletzung:** Falsche Übersetzung → falsches Embedding → falsche Filme. Beispiel: „kitschig" wird zu „cheesy", was im Englischen positive Konnotation hat — verzerrt das Embedding.

**Praktische Risikominderung:** LLM hat im Prompt den Auftrag „fluent English translation". Spot-Checks zeigen vernünftige Übersetzungen.

## A-007 Filmsynopsen sind in Englisch verfügbar

**Annahme:** `payload.overview` ist Englisch (oder zumindest E5-kompatibel). Deutsche Übersetzungen leben separat in `overview_de`.

**Verletzung:** Wenn ein Film nur deutsche Synopsis hat, würde E5 schlechte Embeddings liefern.

**Schutz:** TMDB liefert standardmäßig Englisch. `enrich_de.py` fügt nur additiv DE-Felder hinzu.

## A-008 OpenAI gpt-5-mini Prompt-Caching ist aktiv

**Annahme:** Bei wiederholten Calls mit identischem System-Prompt cached OpenAI den Input-Token-Stream automatisch. Cached Input kostet ~10% des regulären Input-Preises.

**Verletzung:** Costs steigen 10× pro Call. Erkennbar an Billing-Dashboard.

**Risiko:** OpenAI könnte Caching-Verhalten ändern, oder unser Prompt minimal varieren (Whitespace) → Cache-Miss.

## A-009 Tag-Definitionen sind im System-Prompt vorhanden

**Annahme:** Beim Aufruf von `build_system_prompt(ONT)` werden alle Tags mit ihren Definitionen aus `tag_definitions.json` formatiert. LLM hat im Kontext was jeder Tag bedeutet.

**Verletzung:** Wenn `tag_definitions.json` einen Tag nicht definiert, gibt der Prompt `?` aus → LLM ratet.

**Schutz:** Bei jedem neuen Tag muss `tag_definitions.json` ergänzt werden. Sollte als Pre-Commit-Check existieren (TODO).

## A-010 Streaming-Provider werden korrekt in Payload gespeichert

**Annahme:** TMDB liefert `streaming_providers` als String-Array mit normalisierten Namen („Netflix", nicht „netflix" oder „NETFLIX").

**Verletzung:** Mixed-Case-Inkonsistenz würde Provider-Filter brechen. Beispiel: User wählt „Netflix", payload hat „netflix" → 0 Treffer.

**Schutz:** `enrich_providers.py` normalisiert auf TMDB-canonical names. Vorbedingung dass TMDB konsistent ist.
