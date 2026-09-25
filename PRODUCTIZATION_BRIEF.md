# Vigilant ESP — Productization-Brief v3

*Produkt: Vigilant ESP (Experience Semantic Protocol). Engine codename intern: MindRead V3.*

Stand: 2026-05-15. **Repositioniert nach Competitive-Analyse (Vionlabs).**

---

## TL;DR — die neue Positionierung

> **Vigilant ESP ist die Experience-Intent-Search-Schicht — KEINE neue Content-DNA-Engine.** Wir übersetzen menschliche Suchwünsche („düstere Rachegeschichte mit Happy End", „Filme wie John Wick aber mit weiblicher Hauptrolle") in präzise Treffer gegen jede bestehende Content-Intelligence-Schicht. Bring your own DNA — Vionlabs, Gracenote, eigene Editorial-Tags, oder unsere kostenlose LLM-Extraktion als Fallback.

**Nicht:** „Wir analysieren Filme und erzeugen Mood-Tags."
**Sondern:** „Wir machen Streaming-Suche menschlich. Egal welche Tags euer Katalog schon hat."

---

## Competitive Landscape — Vionlabs (Magenta-Bestandslieferant)

Vionlabs (Stockholm) ist die etablierte Content-DNA-Schicht im europäischen Streaming-Markt. **Deutsche Telekom / MagentaTV ist als Referenzkunde auf deren Webseite ausgewiesen** (Dr. Jörg Richartz, Head of TV Strategy).

| Was Vionlabs verkauft | Was Vigilant ESP verkauft |
|---|---|
| **Backend-Intelligence (JSON-Payloads)** | **Frontend-Experience (Search-API + UI)** |
| Multimodale Video-/Audio-/Dialog-Analyse | Natural-Language-Intent-Extraktion |
| Mood/Emotion/VAD/Pacing-Tags pro Szene | Tone-Shift „wie X aber Y" mit LLM-Anker (Variante Z) |
| Embeddings für Similarity-Suche | Weighted RRF Hybrid-Fusion |
| Smart Lists, Thumbnails, Ad-Break-Points | Wheel-UI für emotionale Disambiguierung |
| Daten fließen in CMS / Recommender / Ad-Server | Daten fließen in Endnutzer-Suchleiste |

**Direkter Wettbewerb auf DNA-Qualität ist verloren** — Vionlabs hat 7+ Jahre R&D und einen $1M+ GPU-Cluster für multimodale Embeddings. Wir bauen das niemals nach.

**Aber: die Frontdoor (= Endnutzer-Suche) ist offen.** Vionlabs verkauft keine Consumer-Search-UI. Magenta hat zwar Vionlabs-Tags, aber wer „Mafiafilme aus den 90ern" tippt, bekommt heute Keyword-Treffer — keine Emotion-Search.

---

## Why we don't (and shouldn't) build multimodal embeddings

| Komponente | Vionlabs | Vigilant ESP |
|---|---|---|
| Video-Frame-Features | VideoMAE / X-CLIP, GPU-cluster | — |
| Audio-Spektrogramme | MFCC + valence-arousal aus Soundtrack | — |
| Dialog-Transkript | ASR + NLP | — |
| Synopsis-Text | — | E5-large-v2 (1024-dim) |
| LLM-Intent-Extraktion (Query → Vektor) | — | **Unser Kern: gpt-5-mini + Variant-Z anchor** |
| Tone-Shift mit Reference-Anker | — | **Unser Kern: 2-Pass-LLM mit Stored-DNA** |

Multimodale Embeddings sind ein $1M+ R&D-Vorhaben (~1-3 GPU-h pro Film, pre-trained Modelle, ffmpeg-Pipeline, Raw-Video-Storage). Vionlabs hat 7 Jahre Vorsprung. **Unsere Strategie: deren Output als Input verwenden, nicht selbst bauen.**

Je besser die DNA-Schicht des Kunden (Vionlabs / Gracenote / eigene), desto besser unsere Suche — ohne dass wir die Analyse-Arbeit machen müssen. Wir sind der Übersetzer, nicht der Analyst.

---

## "Bring your own DNA" — Adapter-Architektur (Roadmap)

Drei Eingangs-Pfade in unsere Engine:

```
┌─ Customer Vionlabs-Daten ─┐
├─ Customer Gracenote ──────┤    ┌──── Adapter (Translator) ────┐
├─ Customer Editorial-Tags ─┼───▶│ vionlabs.yaml + …            │───▶ Qdrant
└─ Customer ohne DNA ───────┘    │ canonical ontology v3        │     (mindread_v3)
                                  └──── fallback: LLM-Extract ───┘
                                                                          │
                                                                          ▼
                                  ┌─ /api/search ────────────────────────────┐
                                  │ Intent-Extraktion · RRF-Fusion · UI      │
                                  └──────────────────────────────────────────┘
```

**Adapter-Pattern (Option B "Translator", empfohlen):**
- Kunde liefert seine bestehenden DNA-Daten in unser `/api/admin/films` Endpoint
- YAML-Mappings in `config/external_mappings/` übersetzen externe Schemata in unsere kanonische Ontologie
- Unsere internen Vektoren (`emotion_sparse 30`, `theme_sparse 88`, `subject_sparse 24`) bleiben source of truth
- Vionlabs VAD-Werte (Valence/Arousal/Dominance) → Plutchik 24 + Wirkung 6 via Translation-Matrix
- Vionlabs Mood-Tags → unsere Moods + Pacing-Buckets
- Vionlabs Multimodal-Embedding → ersetzt unseren `synopsis_dense` (Dim-Anpassung im Schema-Flag)

**Was nicht passiert:** Wir rufen NIE die Vionlabs-API selbst auf. Kein Auth, keine SLA-Abhängigkeit, keine Zahlungsbeziehung zwischen uns und Vionlabs. Kunde nutzt seine vorhandene Vionlabs-Lizenz, pusht uns die Daten.

**Aufwand:** ~2 Tage pro Adapter (Vionlabs, Gracenote, JustWatch …).

---

## Sales-Story für Magenta (Beispiel-Pitch)

> „Magenta zahlt Vionlabs für Content-Intelligence — Mood, Emotion, Pacing, Embeddings. Diese JSON-Payloads liegen in eurem Data-Lake. Aber eure Endnutzer tippen immer noch ‚Action 2024' in die Suchleiste und bekommen Title-Matches. Vigilant ESP nimmt die Vionlabs-Signale plus eure Synopsis und macht daraus eine Suche, die ‚düstere Rachegeschichte mit Happy End' versteht — und ‚Filme wie John Wick aber mit weiblicher Hauptrolle' in 3 Sekunden in eure App liefert.
>
> Wir konkurrieren nicht mit Vionlabs — wir multiplizieren euren Vionlabs-Invest, indem wir aus den Tags eine menschliche Suche bauen. Pilot in 2 Wochen, Production in 2 Monaten."

---

## Was sich am Roadmap-Plan ändert

**Streichen:** alle Initiativen die in DNA-Qualität / Content-Analysis investieren würden. Wir bauen keine Video-Pipeline.

**Priorisieren:**
1. **Vionlabs-Adapter** (2 Tage) — `config/external_mappings/vionlabs.yaml` + `scripts/adapters/vionlabs.py` (Mapper-Modul) + erweiterter `/api/admin/films` Endpoint
2. **Generischer Adapter-Mechanismus** (1 Tag) — sodass weitere Provider (Gracenote etc.) ohne Code-Change addiert werden können, nur via YAML
3. **"Multi-Source Index"** in Qdrant — pro Film kann mehrere DNA-Quellen-Versionen tragen; Default-Source per Tenant-Config
4. **Sales-Demo-Modus** — UI-Toggle „mit Vionlabs / mit Synopsis-LLM" zeigen, damit der Käufer den Quality-Lift live sieht
5. **Pitch-Deck v2** mit neuer Story (statt 60 Folien-Deep-Dive 12 Folien Positioning)

**Beibehalten als Demo-Fallback / Self-Contained:**
- Unsere LLM-Extraktion (gpt-5-mini von TMDB-Synopsis)
- Den ganzen Pipeline-Stack (extract_dna_v3.py, enrich_*.py)
- 15K Demo-Korpus als Out-of-the-Box-Beispiel
- Eval-Suite

---



## Was wir heute haben

- **15.255 Filme** indexiert mit emotionsbasierter DNA (24 Plutchik + 6 Wirkung +
  35 Plot-Themes + 18 Genres + 15 Settings + 10 Archetypes + 12 Moods + 8 Pacing +
  24 Subjects + 10 Content-Features + 6 Color-Palette + 6 Protagonist-Age)
- Hybrid-Search (dense Synopsis-Vektor + sparse Genome-Vektoren) via Qdrant
- LLM-basierte Free-Text-Intent-Extraktion (gpt-5.4-mini, austauschbar)
- Wheel-UI mit Slider für Mix (Plot/Theme/Emotion + Indie/Mainstream + Year/Runtime)
- Multilingual (DE/EN-Query mit Translate-Step)
- Match-Reasons sichtbar pro Treffer (welcher Tag hat zu welchem Score-Anteil beigetragen)
- API + UI in <2.000 Zeilen Code, schnell deploybar

## Was für einen Anbieter NICHT-VERHANDELBAR fehlt

### A. Catalog-Ingestion-Pipeline
**Heute (2026-05-15)**: `POST /api/admin/films` (JSON + CSV-Upload) live, Auth-gated via `X-API-Key`. Max 200/Batch synchron. Größere Kataloge per Client-Batching.
**Bleibt offen**: Async-Job-Queue + Webhook-Pattern für 50K+-Kataloge in einem Call; eigene Adapter pro Lieferantenformat (TVA / MovieLens / Custom-XML).

→ **Aufwand verbleibend**: 3-5 Tage pro Adapter

### B. Multi-Tenant-Trennung
**Heute**: Single Qdrant-Collection.
**Nötig**: Pro Kunde eigene Collection oder Tenant-Tag, abgeschlossene Daten/Telemetrie. SaaS-Modell oder On-Prem.

→ **Aufwand**: 2-3 Tage Architektur, Auth-Layer, Routing

### C. Authentifizierung + Rate-Limiting
**Heute (2026-05-15)**: API-Key-Auth auf `/api/admin/*` live (`ADMIN_API_KEYS` env, komma-separiert). Search-Endpoint noch offen — Reverse-Proxy-Gate beim Käufer empfohlen.
**Nötig**: Quota-Management (Redis-Counter pro Key), Audit-Log, optional JWT-Tenant-Isolation.

→ **Aufwand verbleibend**: 1-2 Tage Quota+Audit

### D. Streaming-Verfügbarkeit ist Pflicht
**Heute**: Nicht implementiert.
**Nötig**: User will sehen „auf MEINEM Konto verfügbar". Anbieter weiß das selbst —
Daten kommen aus seinem Katalog. Filter im Search-Endpoint.

→ **Aufwand**: 1 Tag wenn Daten im Katalog, sonst Provider-Mapping über JustWatch-API

### E. Serien-Support
**Heute**: Nur Filme.
**Nötig**: Serien sind 70 % der Streaming-Nachfrage. DNA pro Serie
(eventuell pro Season) extrahieren, Series-Filter, „erste Folge"-Lookup.

→ **Aufwand**: 5-10 Tage, evtl. eigene DNA-Schema-Erweiterung („Episodendichte",
„Cliffhanger-Anteil", „Story-Arc" Tag)

### F. Performance-Garantien
**Heute**: ~50 ms similar_to, 3-5 s Free-Text, single-tenant-CPU.
**Nötig**: <500 ms p95 für Free-Text. Heißt: Qwen lokal auf GPU oder
gpt-5.4-mini mit Prompt-Caching + Edge-Cache. Plus horizontal-skalierbares
Qdrant-Cluster (>5K QPS).

→ **Aufwand**: 1-2 Wochen, GPU-Capacity oder OpenAI-Volume-Vertrag

### G. Personalisierung
**Heute**: Stateless, kein User-Profil.
**Nötig**: Kollaborative Komponente — „Leute mit ähnlichem Geschmack mochten X".
Mindestens „watched"-Tracking + Avoid-Liste pro User.

→ **Aufwand**: 5-10 Tage, neuer Storage-Layer (Postgres / Redis)

### H. Editorial-Override
**Heute**: Reine Algorithmus-Empfehlung.
**Nötig**: Anbieter wollen pinnen können („Diese Woche promoten wir X"), bestimmte
Genres downranken, eigene Listen kuratieren. Admin-UI.

→ **Aufwand**: 5-10 Tage

### I. Compliance + Privacy
**Heute**: Keine Telemetrie, keine Cookies, keine User-Daten.
**Nötig**: GDPR/DSGVO-konformes Tracking, Opt-In-Logging, Data-Deletion-Rights,
ISO 27001/SOC2 falls Enterprise. Pseudonyme User-IDs, kein Klartext.

→ **Aufwand**: ongoing, externe Compliance-Beratung

### J. Observability
**Heute**: Plain stdout-Logs.
**Nötig**: Prometheus-Metriken (latency p95, error rate, LLM-spend per tenant),
strukturierte JSON-Logs, ELK/Loki, Tracing für Debug.

→ **Aufwand**: 3-5 Tage

## Was UNGEWÖHNLICH ist und ein Verkaufsargument

- **Match-Reasons sind sichtbar** — kein Black-Box. „Warum dieser Film? Weil
  query.cathartic 22 % × film.cathartic 30 % = 6.6 % Beitrag…". Anbieter mögen
  Erklärbarkeit.
- **Wheel-UI als USP** — niemand sonst hat das visuell so. Vor allem TV-Plattformen
  könnten das auf Smart-TV mit Fernbedienung gut bedienen.
- **Domain-Ontologie statt rein ML** — 128 kuratierte Tags, keine 10K-Embeddings
  ohne Kontrolle. Anbieter können Ontologie selbst tunen (z.B. „Tatort-Krimi"
  als deutscher Theme-Tag).
- **Kompakt und White-Labelable** — 2K Zeilen Code, kein TF/PyTorch-Training nötig.

## Hardware-Sizing (gemessen + extrapoliert)

Engine läuft als 2-Container-Bundle (api + qdrant). Memory ist der harte Faktor (E5-large-v2 hält 1024-dim Float32-Vektoren in RAM für HNSW).

| Korpus-Größe | RAM (Qdrant) | RAM (API + E5) | CPU | Optionale GPU | Latenz P95 (Free-Text) |
|---|---|---|---|---|---|
| 15 K Filme (Demo) | 1.5 GB | 3 GB | 2 cores | — | 2.5-3 s |
| 50 K Filme | 4 GB | 3 GB | 4 cores | — | 2.5-3 s |
| 200 K (Filme+Serien) | 14 GB | 3 GB | 8 cores | optional GPU für Local-LLM | 2.5-3 s |
| 500 K | 32 GB | 3 GB | 16 cores | empfohlen für ingest | 2.5-3 s |

LLM-Latenz dominiert (~2 s OpenAI gpt-5.4-mini, ~5-100 s Qwen je nach GPU); Vektor-Retrieval ist <50 ms bis 500K (HNSW). Reine `similar_to=id` Searches sind <100 ms (kein LLM).

Empfohlene Cloud-Targets: AWS m6i.xlarge (50 K), m6i.4xlarge (200 K), r6i.4xlarge (500 K). Lokales Setup: jede 16-GB-Workstation reicht für 100 K.

## Onboarding-Checkliste für neue Käufer

Für ein Pilot-Deployment (Catalog ≤ 50 K) in ~2 Tagen:

1. **Day 0** — Bundle übergeben
   - [ ] `docker-compose.yml` + `Dockerfile` + `requirements.txt` + Engine-Code (~ 2 K LOC)
   - [ ] `LICENSE` + `THIRD_PARTY_NOTICES.md` + `LICENSES_MANIFEST.md`
   - [ ] `.env.example` mit allen Env-Variablen dokumentiert
   - [ ] API_GUIDE.md + LLM_PROVIDERS.md + USER_GUIDE.md
2. **Day 1** — Kunde deployt
   - [ ] `docker compose up -d` — Qdrant + API hoch in <5 min
   - [ ] `OPENAI_API_KEY` und `ADMIN_API_KEYS` in `.env` setzen
   - [ ] `curl /api/health` zeigt `status: healthy`
3. **Day 1-2** — Catalog-Ingest
   - [ ] Catalog als CSV (Pflichtspalten: tmdb_id, title, overview)
   - [ ] In 200er-Batches via `POST /api/admin/films/csv`
   - [ ] LLM-Extract-Cost ≈ $0.0003 / Film (OpenAI)
   - [ ] 50 K Filme = ~$15, ~70 min Laufzeit (synchron mit 20 Workern Client-Side)
4. **Day 2** — Frontend-Integration
   - [ ] `frontend/index.html` als Referenz-Implementation; Kunde embedded in eigene UI
   - [ ] `POST /api/search` ist einziger Live-Endpoint
   - [ ] Wheel-UI optional über `GET /api/ontology` selbst rendern
5. **Day 2+** — Eval
   - [ ] `scripts/eval_predictable.py` mit ~ 20 kundenspezifischen Queries adaptieren
   - [ ] Pass-Rate ≥ 80 % als Akzeptanz-Kriterium

## Support-Tier-Modell

| Tier | Reaction | Kontakt | Pro Jahr |
|---|---|---|---|
| **Bronze** | 5 Werktage E-Mail | info@vigilant-crs.de | inkl. License |
| **Silver** | 2 Werktage E-Mail + Slack | dediziertes Slack | +15 % License |
| **Gold** | 4 h Business Hours (CET) | Slack + Phone | +30 % License |
| **Platinum** | 1 h Critical (24/7) + monatliches Architecture-Review | direct line | +50 % License |

Maintenance/Updates (Bug-Fixes, Sicherheits-Patches, neue Modelle) sind in allen Tiers enthalten. Major-Version-Upgrades (Schema v3+) sind separat per Change-Request.

## Entry-Pricing-Modell

- **Setup**: 30-60K€ für Catalog-Ingestion + Tenant-Setup
- **SaaS-Recurring**: 0.5-2 ct pro Search-Call (LLM-Cost + Marge), bei 1M Searches/Monat
  ≈ 5-20K€/Monat
- **On-Prem-License**: 100-300K€/Jahr, Kunde betreibt eigene Hardware
- **Custom-Ontology-Tuning**: 10-30K€ Einmalprojekt
- **Support-Tier**: siehe oben, +15/30/50 % auf License-Fee

## Was als nächstes Sinn ergibt für ein Demo-Pitch

1. **Quality-Eval-Suite** so bauen, dass sie Anbieter-Catalogs durchläuft (CSV-In,
   Pass/Fail-Report). Beweist: „Funktioniert auch auf eurem Katalog."
2. **Streaming-Verfügbarkeits-Filter** mocken — minimal viable, mit beliebiger
   provider-Liste in Payload.
3. **Serien-DNA-Extraktion-PoC** — 50 deutsche Serien per LLM extrahieren, zeigen
   dass Pipeline trägt.
4. **Mobile-tauglicher Wheel-UI** — TV-First-Variante (Fernbedienung-navigierbar).
5. **Eine Demo-Catalog-Größe von ≥50K Items** — TMDB-Bulk aus 20K + Open-Subtitles
   für Serien-Pool oder Wikidata.

Damit hat man ein vorzeigbares Pilot-Setup in 4-6 Wochen.
