# Open Theoretical Gaps

Was wir theoretisch nicht geklärt haben. Nicht „Bugs", sondern fehlende Begründungen oder Beweise.

## G-001 Optimale Tone-Shift-Blend-Ratio

**Frage:** Ist 60/40 optimal? Wie würde man das beweisen?

**Theoretischer Ansatz:** Bayesian inference über User-Click-Through-Data — bei welcher Ratio klickt User am häufigsten Top-Result?

**Status:** Daten fehlen (kein Click-Tracking aktiv). Heuristisch getuned auf Eval-Edge-Cases.

## G-002 Wann ist Subject „prominent genug" für Tag-Setting

**Frage:** Bei „The Departed" → mafia=1.0 klar. Bei „Lethal Weapon 2" mit Mob-Subplot → mafia=0.3? 0.5? Gar nicht?

**Theoretisches Problem:** „Prominenz" ist nicht formal definiert. LLM macht eine subjektive Einschätzung.

**Status:** offen. Aktuelle Anweisung „CENTRAL to the film" — schwammig.

## G-003 Wieviele Subjects pro Film sind „natürlich"?

**Frage:** Aktuell 0-3 erlaubt. Aber empirisch sehen wir Filme mit subjects = {mafia:0.375, prison_life:0.375, espionage:0.25} — drei Sujets parallel. Ist das richtig?

**Theoretisch:** Ein Film hat ein primäres Sujet plus optional sekundäre. Eine Power-Law-Verteilung der Weights wäre erwartbar.

**Status:** offen. Beobachten was Qwen-Output liefert, ggf. Prompt zu „0-2 entries" einengen.

## G-004 Cross-Channel Score-Vergleichbarkeit

**Frage:** Wie vergleichbar sind die Scores aus synopsis_dense vs emotion_sparse vs theme_sparse? RRF dämpft Rang-basiert, aber die Rang-Verteilungen können sich pro Channel stark unterscheiden.

**Konkret:** Was wenn der Top-Rank in synopsis_dense Score 0.85 hat, während der Top-Rank in theme_sparse 0.45 hat? RRF behandelt sie gleich (beide rank=1), aber die „Konfidenz" ist sehr unterschiedlich.

**Status:** offen. Score-Calibration-Studie wäre nötig.

## G-005 Eval-Test-Validität bei Property-Tests

**Frage:** Wenn wir auf Property-Tests umstellen („mindestens 3 Filme mit subjects.X > 0.3"), wie misst man dann „semantische Korrektheit"?

**Problem:** Property-Tests können trivial gemacht werden indem man Properties wählt die ohnehin gelten.

**Theoretischer Ansatz:** Human-judged Gold-Set + Property-Test korrelieren.

**Status:** offen, aufwendig.

## G-006 Synonym-Decay-Wert empirisch begründet?

**Frage:** Warum 0.7 statt 0.5 oder 0.9?

**Theoretischer Ansatz:** Information-Theory — wieviel Information-Verlust beim Synonym-Mapping? Empirisch: A/B-Tests mit verschiedenen Decay-Werten.

**Status:** offen. 0.7 ist Tradition aus v1, nie ernsthaft hinterfragt.

## G-007 Diversity-Penalty Lambda

**Frage:** β=0.3 in MMR-ähnlichem Diversity-Rerank. Wie wurde das gewählt?

**Theoretischer Ansatz:** Optimierungsproblem: maximize Σ score_i unter Constraint cosine-distance > τ zwischen Top-N.

**Status:** offen. Aktuelle 0.3 ist Best-Guess.

## G-008 RRF-Konstante k=60

**Frage:** Cormack et al. nehmen k=60 als Default. Ist das für unsere Channel-Mischung optimal?

**Hintergrund:** k dämpft Top-Ranks. Kleines k = top-heavy, großes k = flacher.

**Status:** offen. Standard-Wert übernommen ohne Tuning.

## G-009 Emotion-Wirkung-Joint-Normalisierung — semantisch korrekt?

**Frage:** Wir normalisieren emotions(24) + wirkung(6) GEMEINSAM auf L1=1.0. Aber emotion ist „what the protagonist feels", wirkung ist „what the viewer feels". Semantisch zwei verschiedene Dinge — sollten sie separat normalisiert werden?

**Konsequenz aktueller Implementation:** Ein Film mit viel cathartic-wirkung würde wenig „room" für emotion-tags haben.

**Status:** offen. Pragmatisch funktioniert es, theoretisch fragwürdig.

## G-010 LLM-Determinismus theoretisch erreichbar?

**Frage:** Mit Temperature=0 und Seed-Fixierung sollte LLM deterministisch sein. Empirisch ist es nicht — OpenAI behält sich „Server-side fingerprint" vor.

**Theoretisch:** Streng deterministische LLM-Inference ist möglich (gleiche Hardware, gleiche Software, fixierte Seeds). In Produktion (verteilte API) nicht garantiert.

**Status:** offen. Mitigation: Multi-Run-Averaging im Eval.

## G-011 Subject-Channel Score-Gewichtung im Theme-Bucket

**Frage:** Subjects haben L1=1 separat normalisiert. Plot_themes+genres haben L1=1 jointly. Settings, moods, pacing je L1=1. Total theme_sparse L1 ≈ 5.

**Gewichtung implizit:** Subject-Channel trägt 1/5 der Theme-Score bei. Ist das richtig? Sollte ein expliziter Subject-Tag stärker wirken als ein Theme-Tag?

**Status:** offen. Bei Subject-Queries empirisch ausreichend, könnte aber gestärkt werden.

## G-013 (Audit 2026-05-12) Weighted-RRF ≠ klassisches RRF

**Frage:** Cormack et al. 2009 definieren RRF als `Σ_c 1/(k+rank_c)` OHNE Channel-Gewichtung. Unsere Implementation ist `Σ_c w_c · 1/(k+rank_c)` — **weighted RRF**, eine Eigen-Erweiterung. Wir etikettieren sie in THEORY_REGISTRY.md T-004 als „standard_method (RRF)".

**Theoretische Konsequenz:** Skaleninvarianz-Argument von Cormack gilt strikt nur ohne Gewichte. Mit Gewichten ist die Aggregation noch immer rang-basiert, aber die rejected mass kann je nach Gewichts-Verteilung bestimmten Channels Übergewicht geben.

**Was zu prüfen:** Welche formalen Eigenschaften von klassischem RRF erhalten bleiben bei `weighted RRF`. Vermutlich Ordnungs-Invarianz innerhalb eines Channels, aber nicht zwischen Channels.

**Empfehlung:** In agent-memory umetikettieren — `engineering_extension` statt `standard_method`.

**Status:** open, Theorie-Etikettierung-Frage.

## G-014 (Audit 2026-05-12) Mischung absolute Boost auf Rang-Score

**Frage:** Nach RRF-Aggregation werden absolute Werte addiert: `popularity_boost · 0.01 · pop_norm` und `-avoid_penalty · mass · 0.02`. Diese sind NICHT rang-basiert.

**Konsequenz:** RRF-Score-Magnitude variiert mit Anzahl der Channels (3 Channels → max Score ≈ 0.05; 1 Channel → max ≈ 0.016). Absolute Boosts ≈ 0.01 sind also bei 1-Channel-Mode 62% des Top-Scores, bei 3-Channel-Mode 20%.

**Effekt:** Slider-Verhalten ist nicht slider-unabhängig.

**Lösungsansätze:**
- (a) Boost als Multiplikator auf Score statt Addition: `score *= (1 + popularity_boost · 0.5 · pop_norm)`
- (b) Boost als zusätzlicher RRF-Channel modellieren (Rang nach Popularity)
- (c) Boost-Magnitude an Channel-Anzahl skalieren

**Status:** open, mittlerer Aufwand.

## G-012 Kalibrierung von Match-Reason-Confidence

**Frage:** Match-Reasons werden als qw × fw = contribution dargestellt. Sind diese Werte für den User interpretierbar? Was ist „gut" (0.05? 0.20?)?

**Status:** offen. UI zeigt absolute Werte ohne Vergleichsbasis.
