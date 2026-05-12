# Model Limits

Wo das System bekanntermaßen schwach ist. Dokumentiert um falsche Erwartungen zu vermeiden.

## L-001 Subject-Queries mit alten Filmen

**Limit:** Wenn der LLM `subjects.vampire = 1.0` aus einer Query extrahiert, aber alle 7,018 alten Filme im Index kein `subjects`-Feld haben, trägt der Subjects-Channel 0 für sie bei. Die Suche fällt auf E5 + Theme/Genre/Setting zurück.

**Symptom:** Query „Vampirfilme" liefert generisches Horror statt klare Vampir-Filme.

**Fix:** Re-Extract aller alten Filme mit neuer Ontologie ($9, 1h).

## L-002 Content-Features Avoid-Filter ohne Re-Extract

**Limit:** Gleiche Logik wie L-001. Alte Filme haben kein `content_features` → `must_not(content_features.firearms > 0)` trifft sie nicht.

**Symptom:** „Action ohne Schusswaffen" zeigt weiterhin John Wick.

**Fix:** Re-Extract der alten Filme.

## L-003 Quadro P620 zu langsam für Runtime-LLM

**Limit:** Qwen 4B Q5_K_M auf P620: 40-60s pro Query. UI ist nach 5s schon „kaputt" für den User.

**Konsequenz:** `LOCAL_LLM_ENABLED=1` Modus ist im Produkt-Setup deaktiviert. OpenAI bleibt Default.

**Fix:** Stärkere GPU (RTX 4090, A100), oder Quantisierung auf Q3 (Qualität fragwürdig), oder kleinerer Model (Qwen 0.5B testen).

## L-004 LLM-Non-Determinismus bei T=0.1

**Limit:** OpenAI gpt-5-mini bei Temperature 0.1 liefert leicht variierende Outputs für identische Inputs. Eval-Pass-Rate variiert ±5%.

**Symptom:** Aufeinanderfolgende Eval-Runs liefern 25/26/26 Passes mit teilweise unterschiedlichen Top-Ergebnissen.

**Fix-Optionen:**
- Temperature 0.0 testen (kann Output rigide machen)
- Mehrere Eval-Runs mitteln
- Tests in „Property-Tests" umbauen statt fixed-title-Matching

## L-005 Tone-Shift bei subtilen Modifiern

**Limit:** „Inception aber emotional" — der Modifier ist sehr abstrakt. LLM extrahiert oft nur 1-2 schwache Emotion-Tags, 40% Modifier-Gewicht ist evtl. zu schwach.

**Symptom:** Ergebnisse bleiben sehr nah an Inception, Shift kaum spürbar.

**Fix:** Adaptive Blend-Ratio (siehe DISPUTED_POINTS.md DP-008).

## L-006 Genre vs Subject Verwechslung

**Limit:** „Anime Filme" → LLM könnte `genres.Animation` ODER `subjects.anime` setzen. Wenn nur das eine, schwächeres Match.

**Symptom:** Fantasia (Disney, NICHT Anime) kommt hoch wenn LLM nur Animation extrahiert.

**Fix:** Im LLM-Prompt explizit klären: Animation = westliche Trickfilme, anime = japanische Tradition. Aktuell teilweise vorhanden, könnte schärfer.

## L-007 Synonyms-Decay reicht nicht immer

**Limit:** Bei Synonym-Mapping wird Weight × 0.7. Wenn LLM nur Synonyms verwendet (kein kanonischer Tag), bleibt das Signal schwächer.

**Symptom:** LLM extrahiert „organized_crime" statt „mafia" → 0.7 statt 1.0 → schwächeres Ranking.

**Fix:** LLM stärker zur kanonischen Verwendung disziplinieren (mehr Examples im Prompt). Wartet aber auch ohne Fix.

## L-008 E5 versteht Eigennamen nicht „semantisch"

**Limit:** E5 ist auf Web-Pairs trainiert. Filmtitel sind oft idiosynkratisch („Eternal Sunshine of the Spotless Mind"). E5-Match ist Synonyme-basiert, nicht Titel-basiert.

**Symptom:** „Filme wie Eternal Sunshine" findet besser Filme mit ähnlicher SYNOPSIS, nicht Filme die im Geist Spotless-Mind-haft sind.

**Mitigationen:**
- Title-Index für direkte „wie X" Resolution → DNA-Lookup statt Embedding-Match
- E5 trägt nur 30-40% via Slider, Sparse-Channels tragen den Rest

## L-009 LLM kann „avoid X" mis-extracten

**Limit:** Wenn User sagt „Filme MIT Gewalt" und LLM mis-versteht und Gewalt in avoid statt theme schiebt → Empty result.

**Symptom:** Selten beobachtet aber dokumentiert auf Anthropic-Forum für Edge-Cases.

**Mitigation:** Avoid-Tags werden zu canonical gefiltert, ungültige werden silent verworfen. Falls leere Result-Liste, fällt UI auf „keine Treffer" zurück.

## L-010 Wheel-UI versteckt subjects/content_features

**Limit:** Aktuell zeigt das Wheel-UI nur emotion/theme Tags. Subjects und content_features sind nicht in der Tag-Anpassungs-Ansicht sichtbar — User kann sie nicht manuell schieben.

**Symptom:** User der via Free-Text „Vampirfilme" sucht sieht im Wheel keinen „vampire"-Tag den er hin- und herschieben könnte.

**Fix:** UI-Erweiterung um Subjects-Panel.

## L-011 Keine Cast/Director-Suche

**Limit:** „Filme mit Tom Cruise" oder „Tarantino-Filme" funktionieren nur über E5 (wenn Name im Synopsis steht). Es gibt keinen Cast/Director-Index.

**Symptom:** Variable Qualität bei Cast-Queries.

**Fix:** Eigener Person-Index — separate Datenstruktur, nicht im Retrieval-Vektor.

## L-013 (2026-05-12) avoid_content-Filter ist aktuell NICHT FUNKTIONAL

**Limit:** `_filter_to_dict` in `scripts/search_v3.py` serialisiert nur `must`, nicht `must_not`. Konsequenz: `avoid_content`-Filter (firearms, graphic_violence, …) wird beim HTTP-Call an Qdrant silent abgeschnitten und nie angewendet.

**Symptom:** Query „Action ohne Schusswaffen" — LLM extrahiert `avoid_content=["firearms"]`, Engine baut `Filter(must_not=...)`, aber Qdrant sieht es nie. John Wick erscheint weiterhin top.

**Status:** **Bekannter Bug F-001** (siehe CROSS_MODEL_REVIEW CMR-002). Fix-Skizze in agent-memory/CROSS_MODEL_REVIEW.

## L-014 (2026-05-12) `diversify()` kann weniger als limit Filme zurückgeben

**Limit:** Wenn franchise-cap erreicht ist, wird der gepoppte Eintrag mit `continue` übersprungen, aber nicht ins pool zurück. Bei franchise-lastigen Search-Pools schrumpft das Ergebnis unter `limit`.

**Status:** **Bekannter Bug F-002** (CMR-002).

## L-012 Eval-Test-Listen vs. tatsächliche Coverage

**Limit:** Eval-Tests prüfen auf konkrete Filmtitel. Wenn unsere Corpus die erwarteten Filme nicht enthält, schlägt der Test fehl obwohl semantisch korrekte Filme zurückkommen.

**Symptom:** Tests müssten regelmäßig nachjustiert werden je nach Korpus-Inhalt.

**Fix:** Property-basierte Tests (siehe DISPUTED_POINTS.md DP-006).
