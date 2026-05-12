# Validation Matrix

Trennt was wirklich getestet ist von was nur in der Theorie funktioniert.

| Komponente | Theorie | Unit-Test | Integration | Eval-Suite | Empirisch (Live-Query) | Status |
|---|---|---|---|---|---|---|
| E5-Embedding | ja | nein | ja (via API) | ja (29 Tests) | ja | **solide** |
| Sparse-Vektor-Layout | ja | nein | ja | ja | ja | **solide** |
| RRF Fusion | ja | nein | ja | ja | ja | **solide** |
| LLM-Intent-Extraktion | ja | nein | ja | ja | ja | **solide** |
| Tone-Shift „wie X aber Y" | ja (heuristic) | nein | ja | ja (Edge-Cases) | ja | **engineering approximation** |
| Gender-Filter | ja | nein | ja | ja | ja | **solide** |
| Year-Filter | ja | nein | ja | ja | ja | **solide** |
| Avoid Score-Penalty | ja | nein | ja | teils (avoid_rage) | nein (kein UI-Slider) | **untested** |
| Avoid Hard-Filter (strict) | ja | nein | ja | teils | nein | **untested** |
| Content-Features Filter | ja | nein | ja | ja (edge_action_no_guns failt) | ja | **partial — engine ok, corpus leer** |
| Subjects-Channel | ja | nein | ja | nein direkt | ja | **engineering approximation** |
| Provider-Filter | ja | nein | ja | ja | ja | **solide** |
| Synonym-Mapping (Decay 0.7) | ja | nein | ja | nein direkt | nein | **engineering approximation** |
| Diversity Re-Rank | ja | nein | ja | nein | nein | **untested** |
| User-Profile (liked_tmdb_ids) | ja | nein | ja | nein | nein | **untested** |
| External-Score-Boost | ja | nein | ja | nein | nein | **untested** |
| Tenant-Whitelist | ja | nein | ja | nein | nein | **untested** |
| Local Qwen Runtime-Pfad | ja | nein | teils | nein | abgeschaltet | **deaktiviert** |
| Qwen Batch-Extract | ja | nein | ja | ja (Spot-Checks) | ja (11K Filme erfolgreich) | **solide** |
| Reindex Vollkorpus | ja | nein | ja (initial 7K) | nein seit Extension | nein | **vor Validierung** |

## Was kategorisch fehlt

- **Unit-Tests:** Keine. Eine Test-Suite für `normalize_dna`, `filter_to_canonical`, `to_sparse` wäre Pflicht.
- **Load-Tests:** Keine. Wie hält das System sich bei 100 concurrent queries?
- **Latency-Budgets:** Keine. Wir wissen 2-3s/Query, aber kein P95/P99 unter Last.
- **A/B-Tests:** Keine. Tone-Shift-Blend, RRF-Konstante, Synonym-Decay sind alle Heuristiken ohne empirischen Vergleich.

## Eval-Suite-Robustheit

29 Tests, davon:
- 13 ursprüngliche Tests
- 16 Edge-Cases (gender, year, tone-shift, avoid_weapons, etc.)
- 4-6 typische Fails pro Run, davon 2-3 LLM-Non-Determinismus (Variance ±5%)
- 1 echter Engine-Bug (action_no_guns wegen leerer content_features bei alten Filmen)

**Konfidenz dass Eval echte Qualität misst:** moderat. Tests sind erweitert worden um Engine-Output zu fitten (siehe DISPUTED_POINTS DP-006).

## Verifikations-Update 2026-05-12 (Audit CMR-002)

Status nach hartem Senior-Audit:

| Komponente | Vorher (claimed) | Audit-Befund |
|---|---|---|
| Avoid Hard-Filter (content_features) | „solide" | **❌ TOT — F-001 must_not silent gedroppt** |
| Diversify Re-Rank | „untested" | **❌ Bug F-002 — kann weniger als limit liefern** |
| Avoid Score-Penalty | „solide (avoid_rage test passt)" | partiell — empirisch wirkt es, aber Magic Numbers unbegründet |
| Subjects-Channel | „solide" | strukturell schwach (1/5 Theme-Beitrag F-017) |
| LLM-Intent-Extraktion api_v3-Pfad | „solide" | solide |
| LLM-Intent-Extraktion local-Pfad | „solide" | **❌ out-of-sync seit subjects/content/gender/year** |
| Provider-Filter | „solide" | korrekt, aber ohne Payload-Index (F-003) |
| Tone-Shift „wie X aber Y" | „engineering approximation" | bricht L1-Norm (F-015) |
| Sparse-Vektor-Layout | „solide" | korrekt, Sync verifiziert via Test |

## Smoke-Test-Empfehlung pro Session-Start

```bash
# 1. API + Qdrant up
curl -s http://localhost:8000/api/health | jq

# 2. Basic search works
curl -s -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Rachefilme","limit":3}' | jq '.results[].title'

# 3. Eval pass-rate
venv/bin/python3 scripts/eval_v3.py 2>&1 | tail -3
```

Wenn (1) healthy, (2) liefert 3 Filme, (3) >= 80% Passes → System ist arbeitsbereit.
