# Derivations

Mathematische Herleitungen, Formeln und Normalisierungen. Wenn etwas verändert wird, **muss** die Formel hier aktualisiert werden.

## D-001 L1-Normalisierung pro Bucket

Für jeden Bucket b mit Tag-Weights {w₁, ..., wₙ}:

```
w_i_norm = w_i / Σ_j w_j         (mit w_j > 0)
```

Resultat: Σ w_norm = 1.0 pro Bucket.

**Implementiert in:** `extract_dna_v3.py::normalize_l1`

## D-002 Theme-Sparse Layout (Konkatenation)

```
theme_sparse[i] = w
wobei i ∈ [0, 111]:
  [0..34]   plot_themes      (35 Tags, L1=1 jointly mit genres)
  [35..52]  genres           (18 Tags, L1=1 jointly mit plot_themes)
  [53..67]  settings         (15 Tags, L1=1)
  [68..79]  moods            (12 Tags, L1=1)
  [80..87]  pacing           (8 Tags, L1=1)
  [88..111] subjects         (24 Tags, L1=1, separately normalized)
```

**Wichtig:** plot_themes + genres werden GEMEINSAM L1-normalisiert (`normalize_l1({**th, **gn})`), nicht separat. Sie repräsentieren die „what is this story about" Achse.

Settings, moods, pacing, subjects sind jeweils separat L1-normalisiert.

**Total L1 von theme_sparse ≈ 5.0** (5 unabhängig normalisierte Sub-Buckets).

## D-003 Emotion-Sparse Layout

```
emotion_sparse[i]:
  [0..23]   emotions      (24 Tags, Plutchik 8×3, L1=1 jointly mit wirkung)
  [24..29]  wirkung       (6 Tags, jointly L1=1)
```

Auch hier joint normalisiert. **Total L1 = 1.0** (einziger Sub-Bucket-Pair).

## D-004 Sparse Dot Product (Match-Score pro Channel)

Für Query q und Film d, beide sparse:
```
score(q, d) = Σ_{i ∈ q.indices ∩ d.indices} q.values[i] · d.values[i]
```

Indices außerhalb des Schnitts tragen 0 bei.

**Implikation für Append-Only:** Wenn d die neuen Indices [88..111] nicht hat (alte Filme ohne subjects), trägt subjects-Channel 0 zur Score bei → der Film wird **nicht** schlechter, nur nicht spezifisch besser.

## D-005 Synonym-Decay-Mapping

Wenn LLM einen nicht-kanonischen Tag `t_noncanonical` liefert:

```
if t_noncanonical in synonyms_inverse_map:
    canonical = synonyms_inverse_map[t_noncanonical]
    weight_canonical += original_weight * 0.7
else:
    drop tag
```

Faktor 0.7 = synonym_decay. Gilt nur einmal — kein iteratives Mapping.

**Implementiert in:** `extract_dna_v3.py::filter_to_canonical`

## D-006 Tone-Shift Blending

Bei resolvedem `similar_to_title`:

```
query_emo[t] = 0.6 · ref_emo[t] + 0.4 · modifier_emo[t]
query_th[t]  = 0.6 · ref_th[t]  + 0.4 · modifier_th[t]
```

Modifier kommt nur aus dem LLM-Output (Delta-Intent). Reference kommt aus dem Qdrant-Payload des aufgelösten Films.

**Property:** Wenn modifier_emo leer ist (pure „wie X" ohne „aber Y"), wird query_emo = 0.6·ref_emo → L1=0.6 (nicht 1.0). Das ist ok weil downstream auch nur dot products gerechnet werden, nicht Wahrscheinlichkeiten.

**Verbesserungsmöglichkeit:** Adaptive Blending je nach Modifier-Stärke (siehe DISPUTED_POINTS.md DP-008).

## D-007 RRF Score Aggregation

Für Query q mit K Channels:

```
score_total(d) = Σ_{c=1..K} w_c · 1/(60 + rank_c(d))
```

mit rank_c(d) = Position von d im sortierten Ergebnis von Channel c (1-indexed).

Konstante 60 ist Cormack et al. 2009 — dämpft Top-Ranks (Rang 1 bekommt 1/61, nicht 1/1).

**Channels und ihre Gewichte:**
- synopsis_dense: w_synopsis (Slider, default 0.35)
- emotion_sparse: w_emotion (Slider, default 0.35)
- theme_sparse: w_theme (Slider, default 0.30)
- user_profile (optional): w_personal (default 0.0)
- external_score_boost (optional): w_external (default 0.0)

## D-008 Avoid Score-Penalty

Für `avoid_emotions = [t₁, ..., tₘ]` und Film mit `film_emo[t]`:

```
penalty = α · Σ_i film_emo[t_i]
score_after_penalty = score_before · (1 - min(penalty, 1))
```

α empirisch ≈ 1.0 (lineares Strafmaß). Wenn Film 100% Avoid-Tag enthält → Score=0.

**Bei `avoid_strict=True`** wird stattdessen hart gefiltert: Film mit ANY avoid_tag > Schwelle wird komplett ausgeschlossen.

**Implementiert in:** `scripts/search_v3.py::manual_weighted_fusion`

## D-009 Indie-Mainstream Popularity-Boost

```
score_boosted = score · (1 + indie_mainstream · log10(1 + popularity))
```

- `indie_mainstream` ∈ [-1, +1] (Slider)
- `popularity` = TMDB-Score, log10-Stauchung um Outliers zu dämpfen
- Bei `indie_mainstream = +1`: Mainstream-Boost
- Bei `indie_mainstream = -1`: Indie-Penalty (de facto invertiert)

## D-010 Diversity Re-Ranking

Implementiert via MMR-ähnlichen Mechanismus: nach Top-K ein zweiter Pass der Filme die zu ähnlich zu schon gewähltem deselectiert.

Genauer: für i-tes Result wird Score adjustiert:

```
score_adj(d_i) = score(d_i) · (1 - β · max_{j<i} cosine(d_i, d_j))
```

β ≈ 0.3 default. β=0 schaltet Diversity ab.

**Status:** engineering approximation, nicht formal evaluiert.

## D-011 Sparse-Vektor-Erweiterung — Kein-Bruch-Theorem

**Behauptung:** Wenn Tag T mit Index n_new = max_existing_index + 1 hinzugefügt wird, dann gilt für jeden gespeicherten Vektor v_old (ohne Index n_new):

```
score(q, v_old) bleibt unverändert für alle q ohne Tag T
score(q, v_old) = score(q', v_old) für q mit Tag T
  wobei q' = q ohne Tag T
```

**Beweis:** Sparse dot product summiert nur über q.indices ∩ v.indices. Da n_new ∉ v_old.indices, trägt der neue Tag in q nichts zu score(q, v_old) bei. ∎

**Konsequenz:** Append-Only-Erweiterung ist nachweisbar safe für Backward-Kompatibilität.
