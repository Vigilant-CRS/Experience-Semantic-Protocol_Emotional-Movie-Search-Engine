# Theory Registry

Theoretische Bausteine des Systems. Status-Marker: `standard_method`, `engineering_approximation`, `heuristic`, `open`, `business_decision`.

## T-001 E5 Dense Embedding (Synopsis-Channel)

**Theorie:** `e5-large-v2` ist ein Dual-Encoder mit query/passage Prefixes. 1024-dim, L2-normalisiert, cosine similarity ≡ dot product. Trainiert auf MSMARCO + Wikipedia Web-Pairs.

**Zweck im System:** Semantische Synopsis-Ähnlichkeit. Fängt:
- Konkrete Subjekte im Plot („vampire", „samurai") wenn das Wort im Synopsis steht
- Eigennamen (Filmtitel, Personen)
- Sprachliche Nuancen jenseits unserer 88-Tag-Ontologie

**Warum E5 statt OpenAI text-embedding-3:**
- Lokal lauffähig, kein API-Cost pro Embedding
- 1024-dim ist Sweet-Spot (kleiner als OAI-3072, behält Qualität)
- Public model, reproduzierbar beim Kunden

**Status:** standard_method

## T-002 Sparse-Vektor-Retrieval mit L1-normalisierten Buckets

**Theorie:** Pro Bucket Tag-Weight-Dict mit Sum=1.0. Sparse-Vektor in Qdrant ist (indices, values)-Liste. Match = Dot-Product = Σ qᵢ·dᵢ.

**Eigenschaft:** Pro Bucket gleiches Stimm-Gewicht — kein Bucket dominiert durch sheer Summe.

**Warum nicht Softmax oder Sigmoid:**
- L1-Norm ist mathematisch konsistent mit Probability-Distribution-Interpretation
- Match-Reasons direkt interpretierbar (qw × fw = contribution)

**Status:** engineering_approximation

## T-003 Plutchik-Wheel als Emotion-Bucket-Basis

**Theorie:** Plutchik (1980) — 8 primäre Emotionsfamilien (joy, trust, fear, surprise, sadness, disgust, anger, anticipation) × 3 Intensitätsstufen = 24 Tags. Plus 6 Wirkung-Tags für viewer impact (cathartic, unsettling, bittersweet, haunting, comforting, inspiring) = 30 total.

**Warum nicht Ekman 6 oder GoEmotions 27:**
- Plutchik hat Familien-Hierarchie mit Intensitäten → erlaubt Slider „Emotionen anpassen"
- GoEmotions 27 zu spezifisch (overlap, dilution)
- Ekman 6 zu grob (kann „rage" nicht von „frustration" trennen)

**Status:** standard_method (Plutchik), engineering_approximation (Wirkung-Erweiterung)

## T-004 Reciprocal Rank Fusion für Multi-Channel-Retrieval

⚠️ **Audit-Korrektur 2026-05-12:** Klassisches RRF (Cormack et al. 2009) ist UNGEWICHTET. Unsere `manual_weighted_fusion` ist eine **gewichtete RRF-Variante** — eine Eigen-Erweiterung, kein klassisches Cormack-RRF. Status entsprechend korrigiert.

**Theorie:** Klassisches RRF gibt jedem Channel gleiches Gewicht: `score(d) = Σ_c 1/(k + rank(d, c))`. Unsere Variante: `score(d) = Σ_c w_c · 1/(k + rank(d, c))`. Konstante k=60 dämpft Top-Ranks.

**Im System:** 3-4 Channels (synopsis_dense, emotion_sparse, theme_sparse, optional user_profile, optional external_score_boost). Gewichte aus Slider.

**Warum RRF statt gewichtete Summe direkt:**
- Rank-basiert ist scale-invariant — Channels haben unterschiedliche Score-Verteilungen
- Robust gegen Ausreißer
- Bewiesen besser als individuelle Channel-Ergebnisse in TREC-Studien

**Status:** engineering_extension (weighted RRF, **eigene Erweiterung** über klassisches Cormack hinaus), engineering_approximation (unsere Channel-Auswahl + Boost-Mischung)

## T-005 Tone-Shift via Reference-DNA-Blending

**Theorie/Heuristik:** Bei „wie X aber Y": LLM extrahiert similar_to_title + Modifier-Tags. Engine lädt Reference-DNA. Blend: query = 0.6·ref + 0.4·modifier.

**Warum 0.6/0.4 statt 0.5/0.5:**
- Reference ist der Anker (User sagte „wie X")
- Modifier ist der Shift (kleiner aber gerichteter Effekt)
- Empirisch getuned, nicht formal optimiert

**Status:** heuristic. Adaptive Variante (proportional zu Modifier-Stärke) ist offen.

## T-006 Synonym-Mapping mit Decay-Faktor 0.7

**Theorie/Heuristik:** Nicht-kanonische Tags des LLM-Outputs werden über `synonyms.json` auf kanonische Tags abgebildet. Weight wird mit 0.7 multipliziert.

**Warum 0.7 statt 1.0:**
- LLM-Synonym = schwächere Aussage als direkter kanonischer Tag
- Penalisiert „faulen" LLM-Output, der sich von Definitionen entfernt
- 0.7 empirisch — verliert nicht zu viel Signal, hält aber Disziplin

**Status:** heuristic

## T-007 Append-Only Sparse-Vektor-Erweiterung

**Theorie:** Sparse-Vektoren sind (index, value)-Listen — keine fixe Dimension. Wenn neuer Tag Index `n+1` bekommt, haben existierende Vektoren dort einfach kein Entry → Beitrag 0 zum Dot-Product.

**Voraussetzung:** Layout-Reihenfolge muss stabil sein. Neuer Bucket nur AM ENDE der Konkatenations-Reihenfolge anhängen. Bestehende Buckets dürfen nicht in der Mitte erweitert werden.

**Konsequenz:** Ontologie ist erweiterbar ohne Re-Index — aber alte Filme bleiben „leer" in neuen Dims, bis sie re-extracted werden. Graceful degradation, kein Bruch.

**Status:** standard_method (Sparse-Theorie), engineering_application (unser Layout)

## T-008 Avoid-Mechanismus mit asymmetrischem Soft/Hard-Hybrid

**Theorie:** Drei Avoid-Typen mit unterschiedlichen mathematischen Realisierungen:
- Emotion/Theme: Score-Penalty multiplikativ — soft, weil LLM-Extract fehlbar
- Content-Features: Qdrant `must_not(field.X > threshold)` — hard, weil binär
- Gender: Qdrant `must(field == X)` — exact match

**Warum nicht uniform:** Verschiedene Avoid-Targets haben verschiedene Sicherheits-Garantien. Strenger Filter bei unsicherer Klassifikation erzeugt User-frustrierende False-Negatives.

**Status:** engineering_approximation

## T-009 Local LLM Quantisierung Qwen3.5-4B Q5_K_M

**Theorie:** GGUF-Quantisierung Q5_K_M = 5-bit mixed-precision mit K-Means-Cluster pro Block. Erhält ~99% der FP16-Qualität bei ~30% der Größe. K_M-Variante bevorzugt critical layers.

**Im System:** Qwen3.5-4B Q5_K_M = 3.0 GB GGUF. Passt knapp in 4 GB VRAM der Quadro P620. Vollständiges GPU-Offload (alle 24 Layer auf CUDA).

**Empirisch:** Pilot-Test John Wick liefert DNA die zum Few-Shot-Beispiel exakt matched (rage/grief/revenge/antihero/dark+gritty+noir).

**Status:** engineering_approximation. Q4_K_M verliert nachweislich Tag-Präzision; Q6_K wäre besser aber 4B Q6 passt nicht in 4GB VRAM.

## T-010 Software-License-Modell

**Theorie/Geschäftsentscheidung:** Verkauf als Software, nicht SaaS. Käufer hostet selbst, integriert eigene Filme.

**Theoretisches Argument:** Streaming-Provider haben (a) eigenen Content (Rights, Kataloge), (b) eigene Infrastruktur, (c) Datenschutz-Bedarf. SaaS würde diese Asymmetrien verletzen.

**Praktisches Argument:** B2B-License-Modell mit Setup + Annual = niedrige Time-to-Sale. Multi-Tenant-SaaS = 4-6 Wochen Extra-Build, viel Operativ-Overhead, kein klarer Kundenvorteil.

**Status:** business_decision, locked
