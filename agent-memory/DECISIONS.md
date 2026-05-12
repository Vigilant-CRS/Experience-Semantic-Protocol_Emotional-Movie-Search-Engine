# Decisions

Hier stehen kanonische Architektur-Entscheidungen mit Begründung. Wenn etwas geändert wird, **muss** die Begründung hier ergänzt oder ersetzt werden — nicht löschen.

## D-001 Hybrid 3-Vektor-Retrieval

**Entscheidung:** Drei orthogonale Vektoren pro Film: `synopsis_dense` (E5, 1024-dim, semantisch), `emotion_sparse` (30-dim, affektiv), `theme_sparse` (112-dim, narrativ+meta).

**Warum drei statt eins:**
- Ein einziger dense Vektor kollabiert alle Signale; User kann nicht steuern was wichtig ist
- Sparse Vektoren erlauben **kontrollierbare** Suche (Slider) und **Explainability** (Match-Reasons pro Tag)
- E5 fängt konkretes (Vampir-Synopsis), Sparse fängt abstraktes (Revenge-Archetyp)

**Warum nicht mehr Vektoren** (z.B. eigener Cast-Vektor):
- Jeder zusätzliche Vektor = 3D-Slider-Komplexität für User
- Cast/Director gehört in eine Person-Index-Lookup, nicht in den Retrieval-Vektor

**Status:** locked, kein Reset ohne starke Begründung.

## D-002 35 Plot-Themes statt v1's 577

**Entscheidung:** Bewusst kleines Theme-Vokabular. 35 narrative Archetypen (revenge, redemption, hero_journey, …), nicht spezifische Subgenres.

**Warum:** V1 hatte 577 Themes mit massiver Überlappung (`gangster_crime`, `mafia`, `organized_crime`). Folgen:
- LLM-Weight-Dilution (Tag-Bedeutung verwässert)
- Query-Drift (zu viele schwache Signale verwischen Ranking)
- Wartungs-Hölle (jede neue Definition kollidiert mit 5 existierenden)

35 abstrakte Archetypen + Synonym-Decay-Mapping erhalten Vielfalt **ohne** kanonischen Bloat.

**Trade-off:** Spezifische Subjekte wie „Mafia" nicht direkt im Theme-Bucket → wurden in eigenem `subjects`-Bucket abgebildet (D-006).

**Status:** locked.

## D-003 English-only E5 Embedding, Übersetzung als Pre-Step

**Entscheidung:** `intfloat/e5-large-v2` (English-only). User-Queries werden vor Embedding via LLM ins Englische übersetzt (`translated_query`-Feld).

**Warum nicht multilingual:**
- Multilinguales E5 hatte Title-Keyword-Bias (Deutsche Suchanfrage matched Englischen Titel wegen Keyword statt Inhalt)
- Saubere Trennung: internes Repräsentations-Layer (EN) vs. Display-Layer (DE oder EN)

**Konsequenz:** Display-Layer arbeitet separat mit `title_de`/`overview_de` Payload-Feldern + Tag-Übersetzungs-Tabelle (`translations_de.json`).

**Status:** locked.

## D-004 Append-Only Sparse-Vektor-Layout

**Entscheidung:** Theme-Sparse ist konkatenierte Bucket-Sequenz: `plot_themes(35) + genres(18) + settings(15) + moods(12) + pacing(8) + subjects(24)`. Erweiterungen **nur am Ende** anhängen.

**Warum:** Sparse-Vektoren in Qdrant speichern (index, value)-Paare. Wenn Tag in mittlerer Bucket eingefügt wird, verschieben sich alle nachfolgenden Indices → existierende gespeicherte Vektoren zeigen auf falsche Tags → Reindex zwingend.

**Append-am-Ende ist safe:**
- Alte Filme haben keine Werte an neuen Indices → 0-Beitrag (no false match, no false exclude)
- Neue Filme populieren die neuen Dims
- Queries mit neuen Tags geben 0 Beitrag für alte Filme — graceful degradation

**Status:** locked. Verletzung dieser Regel = Index-Bruch.

## ⚠️ NOTE on D-005 (Audit 2026-05-12)

**Korrektur durch Audit CMR-002:** Die Behauptung „graceful no-op für alte Filme" ist **derzeit nicht in Wirkung**, weil `_filter_to_dict` (search_v3.py:150-170) das `must_not`-Feld silent droppt. Solange dieser Bug (F-001) nicht gefixt ist, ist content_features-Avoid **komplett deaktiviert** — egal welcher Film extrahiert ist. Die Decision selbst bleibt korrekt; die Umsetzung ist gebrochen. Erst nach F-001-Fix gilt D-005 wieder.

## D-005 Content-Features als Payload-Only

**Entscheidung:** `content_features` (firearms, graphic_violence, sexual_content, drug_use, …) sind **nicht** im theme_sparse Vektor sondern nur im Qdrant-Payload als Dict.

**Warum:**
- Content-Features sind **kategorisch present/absent**, nicht graduell (eine Action-Szene mit Waffen = firearms ist da)
- Werden als **Hard-Filter** verwendet (`must_not(content_features.firearms > 0)`)
- Slider-Gewicht nicht sinnvoll
- Erweiterung absolut risikofrei (kein Index-Impact, kein Layout-Shift)

**Trade-off:** Alte Filme ohne `content_features` Feld passieren den Filter graceful (no-op). Bug bei „John Wick ohne Schusswaffen" bleibt bis Korpus durchgängig content_features hat.

**Status:** locked.

## D-006 Subjects in theme_sparse hinten anhängen (statt Payload)

**Entscheidung:** `subjects` (mafia, vampire, espionage, …) leben **im** theme_sparse Vektor (Indices 88-111), nicht als Payload-only.

**Warum (gegenüber Payload-only):**
- Subjekte gehören semantisch zur **Theme-Achse** (was ist der Film **über**)
- User mit Theme-Slider hoch erwartet dass Subject-Matches mitwirken
- Score-Beitrag (nicht nur Hard-Filter) — ein Mafia-Film mit `mafia: 1.0` UND `criminal_underworld: 0.7` rankt höher als einer mit nur letzterem

**Warum NICHT in plot_themes integrieren:**
- Plot-Themes sind **Archetypen** (siehe D-002). Subjects sind **Sujets**.
- Vermischen würde Bucket-Semantik ruinieren

**Status:** locked.

## D-007 LLM-Intent als zentrale Übersetzung

**Entscheidung:** Jede Free-Text-Query geht durch genau **einen** LLM-Call. Ausgabe: vollständige DNA + Avoid-Listen + Filter-Felder. Slider-Tweaks an extracted Intent ohne weiteren LLM-Call.

**Warum ein Call statt Pipeline:**
- Latenz-Budget: 2-3s/Query mit einem Call; jeder weitere Call = +1-2s
- Konsistenz: ein LLM-Output ist intern konsistent
- Caching: System-Prompt ist konstant → Prompt-Caching wirkt

**Warum Cloud-LLM (gpt-5-mini) statt local:**
- Quadro P620 zu langsam für Runtime (40-60s/Query mit Qwen 4B)
- $0.0013/Query mit Caching ≈ vernachlässigbar
- Lokales Qwen bleibt reserviert für Batch-Extract (siehe D-009)

**Status:** locked, Re-Eval wenn neue GPU.

## D-008 Tone-Shift: 60/40 Reference-Modifier-Blend

**Entscheidung (heuristic):** Bei „wie X aber Y" wird query_emo = 0.6·ref_emo + 0.4·modifier_emo. Gleicher Faktor für query_th.

**Warum nicht 50/50 oder 70/30:**
- Reference ist der Anker, Modifier ist die Shift-Richtung
- 50/50: Ergebnisse driften zu weit vom Reference weg (verliert „wie Amélie"-Charakter)
- 70/30: Modifier wirkt zu schwach, „aber mit Action" verpufft
- 60/40 empirisch getuned auf den eval Edge-Cases

**Status:** heuristic, candidate for adaptive blending (siehe DISPUTED_POINTS.md).

## D-009 Local Qwen 4B nur für Batch-Extract

**Entscheidung:** `extract_dna_v3.py --local-llm --llm-size 4b` für Korpus-Aufbau. Runtime weiterhin OpenAI.

**Warum 4B statt 2B:**
- 2B: 42s/Call, Qualität spürbar weniger präzise (Pilot-Test John Wick: 2B liefert generischere DNA als 4B)
- 4B Q5_K_M: 57-73s/Call, Qualität auf gpt-5-mini-Niveau bei eindeutigen Filmen
- VRAM: 4B Q5_K_M passt knapp in 4034 MiB der Quadro P620 (3705 MiB belegt)

**Warum lokal statt OpenAI für Batch:**
- Korpus-Extract kann über Nacht laufen, kein Latenz-Druck
- Spart $13-22 für die 10K-14K verbleibenden Filme
- Diversifiziert weg von OpenAI-Quota-Risiko

**Status:** valid für Batch. Wechsel zu OpenAI wenn Speed kritisch (siehe SESSION_HANDOFF Empfehlung).

## D-010 Software-Lizenz statt SaaS

**Entscheidung:** Verkaufsmodell ist Software-Lizenz mit Self-Hosted Docker-Bundle, nicht Hosted-SaaS.

**Warum:**
- Streaming-Anbieter zahlen nicht für fremden Katalog (sie haben eigenen)
- Multi-Tenant-Build kostet 4-6 Wochen extra (Auth, Billing, Usage-Limits)
- B2B-Streaming-Kunden bevorzugen Self-Hosting wegen Datenschutz + Content-Rights
- Lizenz-Modell: einmaliger Setup + jährliche Lizenz, niedrige Total Cost of Ownership beim Kunden

**Konsequenz:** Aktuelles Korpus (7K-21K Demo-Filme) ist Marketing-Asset, kein Produkt. Beim Kunden-Deployment wird komplett mit seinem Katalog reindexiert.

**Status:** locked, business-strategic.

## D-011 Avoid-Mechanismen asymmetrisch

**Entscheidung:** Drei verschiedene Avoid-Implementierungen je nach Datentyp:

| Avoid-Typ | Mechanismus | Warum |
|---|---|---|
| `avoid_emotions/themes` | Score-Penalty in manual_weighted_fusion | LLM kann fehl-extrahieren; soft penalty verzeiht |
| `avoid_content` | Qdrant `must_not(content_features.X > 0)` | Content ist binär present/absent, hard filter angemessen |
| `gender` | Qdrant `must(protagonist_gender == X)` | Exakter Wert, klar definiert |
| `avoid_strict=True` | wechselt Score-Penalty zu Hard-Filter | User-Override |

**Warum nicht alles Hard-Filter:**
- LLM-Extraction nicht 100% accurate; Hard-Filter würde False-Negatives erzeugen
- Score-Penalty ranked relevant statt zu eliminieren

**Status:** locked.

## D-012 GPT-5-mini als Default-LLM

**Entscheidung:** OpenAI `gpt-5-mini` (gpt-5.4-mini Variante) als Runtime + Extract-LLM.

**Warum nicht GPT-5 oder Claude:**
- gpt-5-mini Cost-Effizienz: $0.0013/Call mit Caching
- gpt-5: 5-10× teurer ohne nennenswerten Qualitätsgewinn für unsere Aufgabe (strukturierte Tag-Extraktion)
- Claude: vergleichbare Qualität, aber kein klarer Vorteil; OpenAI ist etabliert

**Eskalation:** Bei Qualitätsproblemen → gpt-5 (full) testen, dann ggf. Claude Sonnet.

**Status:** valid, periodisch reevaluieren.
