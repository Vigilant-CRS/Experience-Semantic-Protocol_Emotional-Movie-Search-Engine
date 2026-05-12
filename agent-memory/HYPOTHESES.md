# Hypotheses

Was wir glauben, aber nicht beweisen können. Wenn etwas hier zu einem Fakt wird (z.B. durch Eval-Daten), wandert es nach `FACTS.md`.

## H-008 (2026-05-12) Hypothese DURCH CMR-002 widerlegt: avoid_content funktioniert

Vor 2026-05-12 nahmen wir an dass `avoid_content`-Filter funktioniert. **Audit F-001** hat empirisch verifiziert dass `_filter_to_dict` das `must_not`-Feld silent droppt → Filter erreicht Qdrant NIE. Diese Annahme war falsch. Korrigiert: avoid_content tat NICHTS bis F-001 gefixt wird.

## H-009 (2026-05-12) Weighted-RRF-Skaleninvarianz möglicherweise nicht erfüllt

**Hypothese:** Unsere `manual_weighted_fusion` aggregiert nicht nur Rang-Beiträge, sondern addiert auch absolute popularity-Boosts (±0.01) und Avoid-Penalty (-mass·0.02). Das könnte die behauptete RRF-Skaleninvarianz verletzen.

**Evidenz pro:** Bei single-channel (w_synopsis=1.0) ist max RRF-Score ≈ 1/(60+1)=0.016. Popularity-Boost +0.01 ist 62% davon. Bei 3 Channels mit gleicher Gewichtung wäre Score ≈ 0.05, Boost +0.01 nur 20%. → Effekt der Boost-Slider variiert mit Channel-Konfiguration.

**Wie verifizieren:** A/B-Run mit identischer Query, einmal mit w_synopsis=1.0 und einmal mit (0.35, 0.35, 0.30). Indie-Slider auf +0.5. Vergleichen ob die Ergebnis-Reihenfolge konsistent erklärbar ist.

**Status:** open, niedrige Priorität.

## H-001 Qwen 4B Q5_K_M ≈ gpt-5-mini für DNA-Extraktion

**Hypothese:** Die DNA, die Qwen 4B lokal liefert, ist semantisch gleichwertig mit der gpt-5-mini-DNA aus dem ursprünglichen 7K-Korpus.

**Evidenz pro:** Pilot-Test John Wick liefert exakt das Few-Shot-Pattern. Spot-Checks auf Anvil/Detective Conan/Time for Bravery zeigen plausible DNA.

**Evidenz contra:** Keine Side-by-Side-Eval zwischen Qwen-Extract und gpt-5-mini-Extract auf identischen 100 Filmen.

**Wie verifizieren:** Re-Extract eine Stichprobe von 50 Filmen, die Qwen schon hat, mit gpt-5-mini. Vergleiche Tag-Overlap, Cosine-Similarity der theme_sparse Vektoren.

**Was hängt davon ab:** Wenn Qwen schlechter ist, sollten wir alle 14K via OpenAI re-extracten ($13).

## H-002 60/40 ist optimaler Tone-Shift-Blend

**Hypothese:** Bei „wie X aber Y" liefert 60% Reference + 40% Modifier die besten Ergebnisse.

**Evidenz pro:** Eval-Tests `edge_amelie_more_action`, `edge_john_wick_female_lead` passen.

**Evidenz contra:** Bei extremen Shifts („Amélie aber mit ULTRA viel Action") wirkt 40% Modifier evtl. zu schwach. Bei subtilen Shifts („Inception aber emotional") evtl. zu stark.

**Wie verifizieren:** A/B-Test mit Slider 30/70, 50/50, 70/30 auf festen Edge-Cases.

## H-003 Subjects-Tag wirkt linear stark genug ohne eigenen Slider

**Hypothese:** Subjects in theme_sparse zu integrieren (anstelle eines eigenen subjects_sparse Channels) reicht für gute Such-Qualität.

**Evidenz pro:** Mafia/Espionage-Queries funktionieren empirisch. Korrekte Filme erscheinen wenn das Subject-Tag den Score-Beitrag liefert.

**Evidenz contra:** Bei Subject-fokussierten Queries (User will wirklich nur Vampirfilme) konkurriert das Subject-Signal mit themes/genres/settings/moods/pacing innerhalb des Theme-Channels — vielleicht ein eigener Channel mit eigenem Slider wäre stärker.

**Wie verifizieren:** Subjects als eigenen Sparse-Vektor implementieren, eval-vergleichen.

## H-004 11K JSONL = ~9K verwertbare neue Filme

**Hypothese:** Von den 11,085 Zeilen im JSONL sind nicht alle eindeutig — Resume-Runs könnten Duplikate haben.

**Evidenz pro:** Resume-Mechanismus dedupiert nach tmdb_id beim Schreiben aber nicht beim Reindex. Bei mehreren Resume-Zyklen mit Crash könnte JSONL doppelte Entries enthalten.

**Wie verifizieren:** `cut -f tmdb_id ... | sort -u | wc -l` gegen `wc -l`.

## H-005 LLM-Non-Determinismus erklärt 4-6% Eval-Varianz

**Hypothese:** Bei Temperature 0.1 produziert OpenAI gpt-5-mini leicht unterschiedliche Outputs für identische Queries. Daher rutschen Eval-Tests an der Grenze hin und her.

**Evidenz pro:** Drei aufeinanderfolgende Eval-Runs an einem Tag: 25/26/26 Passes.

**Evidenz contra:** Keine, aber Quantifizierung fehlt.

**Wie verifizieren:** 10× selben Test mit selben Query, Stddev der Pass-Rate messen. Wenn signifikant, T=0 testen oder Seed-Override versuchen.

## H-006 GPU-Reindex ist möglich nach CUDA-Toolkit-Install

**Hypothese:** E5 läuft auf GPU sobald `torch.cuda.is_available() == True`. Vor 2026-05-04 war das nicht der Fall (Driver-Modul-Mismatch). Jetzt vermutlich ja.

**Evidenz pro:** Driver 580 + CUDA Toolkit 12.0 + llama-cpp CUDA Build funktioniert.

**Evidenz contra:** PyTorch-Build im venv ist evtl. CPU-only — separate Frage von llama-cpp.

**Wie verifizieren:** `venv/bin/python3 -c "import torch; print(torch.cuda.is_available())"`. Wenn False, `pip install torch --index-url https://download.pytorch.org/whl/cu121`.

## H-007 Korpus-Mix (alt+Qwen+fehlend) ist suboptimal für B2B-Demo

**Hypothese:** Wenn der Käufer Demo sieht und nach „Vampirfilmen" sucht, kriegt er schwache Ergebnisse weil 7K alte Filme keine subjects haben. Das untergräbt Demo-Glaubwürdigkeit.

**Evidenz pro:** Empirisch sind Vampir/Knast-Queries genau wegen dieser Inkonsistenz schwach (0/3 echte Treffer).

**Empfehlung:** $22 für Komplett-Re-Extract ausgeben → Demo wird wasserdicht.
