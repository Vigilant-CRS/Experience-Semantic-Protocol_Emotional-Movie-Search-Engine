# MindRead — Productization-Brief

Stand: 2026-05-04. Was fehlt aus dem aktuellen MVP, um es an einen
Streaming-Anbieter (Magenta TV, Maxdome, Joyn, RTL+, …) zu verkaufen.

## Was wir heute haben

- 7.018 Filme indexiert mit emotionsbasierter DNA (24 Plutchik + 6 Wirkung +
  35 Plot-Themes + 18 Genres + 15 Settings + 10 Archetypes + 12 Moods + 8 Pacing)
- Hybrid-Search (dense Synopsis-Vektor + sparse Genome-Vektoren) via Qdrant
- LLM-basierte Free-Text-Intent-Extraktion (gpt-5.4-mini, austauschbar)
- Wheel-UI mit Slider für Mix (Plot/Theme/Emotion + Indie/Mainstream + Year/Runtime)
- Multilingual (DE/EN-Query mit Translate-Step)
- Match-Reasons sichtbar pro Treffer (welcher Tag hat zu welchem Score-Anteil beigetragen)
- API + UI in <2.000 Zeilen Code, schnell deploybar

## Was für einen Anbieter NICHT-VERHANDELBAR fehlt

### A. Catalog-Ingestion-Pipeline
**Heute**: Wir leben von TMDB-Synopsen + LLM-DNA-Extract.
**Nötig**: Anbieter bringt seinen eigenen Katalog (50K–500K Items, Filme + Serien) mit:
- Eigene IDs (nicht TMDB)
- Eigene Synopsen / Editorials (oft besser als TMDB!)
- Eigene Bilder/Poster-CDN
- Eigene Sprach-/Lokalisierungs-Versionen
- Lieferung via TVA, MovieLens-CSV, oder REST/Webhook

→ **Aufwand**: 5-10 Tage, Adapter pro Lieferantenschnittstelle

### B. Multi-Tenant-Trennung
**Heute**: Single Qdrant-Collection.
**Nötig**: Pro Kunde eigene Collection oder Tenant-Tag, abgeschlossene Daten/Telemetrie. SaaS-Modell oder On-Prem.

→ **Aufwand**: 2-3 Tage Architektur, Auth-Layer, Routing

### C. Authentifizierung + Rate-Limiting
**Heute**: Keine Auth (offene API).
**Nötig**: API-Keys pro Tenant, Quota-Management, Audit-Log.

→ **Aufwand**: 2 Tage (FastAPI-Middleware + Redis-Counter)

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

## Entry-Pricing-Modell (Diskussion)

- **Setup**: 30-60K€ für Catalog-Ingestion + Tenant-Setup
- **SaaS-Recurring**: 0.5-2 ct pro Search-Call (LLM-Cost + Marge), bei 1M Searches/Monat
  ≈ 5-20K€/Monat
- **On-Prem-License**: 100-300K€/Jahr, Kunde betreibt eigene Hardware
- **Custom-Ontology-Tuning**: 10-30K€ Einmalprojekt

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
