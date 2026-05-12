# MindRead V3 — Agent Memory

Persistentes Projektgedächtnis. Wird von jedem Agent (Claude, Codex, etc.) **vor** jeder Code-Arbeit gelesen und **nach** wesentlichen Änderungen aktualisiert.

## Lesereihenfolge (top-down)

1. **`PROJECT_OVERVIEW.md`** — was MindRead ist, an wen verkauft wird, was der Kern-USP
2. **`CURRENT_STATE.md`** — was steht jetzt, was läuft, was fehlt
3. **`SESSION_HANDOFF.md`** — was wurde zuletzt gemacht, was kommt als nächstes
4. **`DECISIONS.md`** — kanonische Architektur-Entscheidungen mit Begründung
5. **`FACTS.md`** — objektive Wahrheiten (Zahlen, Endpoints, Dateipfade)
6. **`HYPOTHESES.md`** — was wir glauben aber nicht beweisen können
7. **`DISPUTED_POINTS.md`** — offene Designfragen
8. **`THEORY_REGISTRY.md`** — verwendete Theorien (E5, Plutchik, RRF, Sparse Vektoren)
9. **`FORMAL_ASSUMPTIONS.md`** — Annahmen unter denen das System funktioniert
10. **`DERIVATIONS.md`** — Formeln, Normalisierungen, Mischungsfaktoren
11. **`MODEL_LIMITS.md`** — wo das System bekanntermaßen scheitert
12. **`VALIDATION_MATRIX.md`** — was getestet ist, was nicht
13. **`EVIDENCE_LOG.md`** — konkrete Belege (Eval-Ergebnisse, Benchmarks)
14. **`THEORY_TO_CODE_MAP.md`** — welche Datei welche Theorie umsetzt
15. **`OPEN_THEORETICAL_GAPS.md`** — was noch ungeklärt ist
16. **`CROSS_MODEL_REVIEW.md`** — Beobachtungen anderer Modelle
17. **`HELP_MANUSCRIPT.md`** — Anweisungen für den nächsten Agent

## Schreibregel

**Strikt trennen:**

| Kategorie | Wo | Beispiel |
|---|---|---|
| Fakt | `FACTS.md` | "API läuft auf Port 8000" |
| Hypothese | `HYPOTHESES.md` | "Qwen 4B Qualität ≈ gpt-5-mini" |
| Theorie | `THEORY_REGISTRY.md` | "Plutchik 8×3 Emotionsfamilien" |
| Heuristik | `DECISIONS.md` mit Marker `heuristic` | "60/40 Tone-Shift-Blend" |
| Entscheidung | `DECISIONS.md` | "English-only Embedding" |
| Streitpunkt | `DISPUTED_POINTS.md` | "Subjects eigener Slider?" |

Nie Hypothese als Fakt schreiben. Nie Heuristik als Theorie ausgeben.
