# Project Overview

*Produkt-Name außen: **Vigilant ESP** (Experience Semantic Protocol).
Engine-Codename intern: **MindRead V3** — dieser Name bleibt in Python-Modulen, Qdrant-Collection, Env-Variablen und internen Docs.*

## Was Vigilant ESP / MindRead ist

Semantische Filmsuchmaschine, die nicht über Genres sucht, sondern über **emotionale + thematische DNA**. Statt „Action-Film" tippt der Nutzer „düstere Rachegeschichte mit Happy End" oder „Filme wie John Wick aber mit weiblicher Hauptrolle aber ohne Schusswaffen".

Das Theorie-Paper "Vigilant Experience Semantic Protocol" liefert die wissenschaftliche Untermauerung; diese Software ist die Reference-Implementation.

## Was es nicht ist

- **Kein SaaS-Empfehlungssystem.** Wir verkaufen kein Filmverzeichnis.
- **Kein Recommender.** Wir empfehlen nicht auf Basis von Nutzerprofilen, sondern auf Basis der **expliziten Suchanfrage**.

## Geschäftsmodell

**Software-Lizenz an Streaming-Anbieter** (Magenta TV, Maxdome, Joyn, Sky etc.).

Der Käufer bekommt:
- Docker-Bundle (Self-Hosted, Tenant-isoliert)
- Plug-and-Play Ingest-Endpoint für **seinen** Katalog
- API + Frontend
- Ontologie-Pipeline reproduzierbar

Das aktuelle 21K-Filmkorpus ist **Demo-Asset**, nicht Produkt. Käufer reindiziert mit eigenen Filmen.

## Kern-USP

Drei differentiatoren gegenüber Standard-Filmsuche:

1. **Wheel-UI mit Slider-Mix** — User gewichtet selbst Synopsis ↔ Emotion ↔ Theme. Andere Engines geben nur eine fixe Rangfolge.
2. **„Wie X aber Y"** — Referenzfilm + Modifier. LLM extrahiert nur die Delta-Intent, Reference-DNA wird aus Qdrant geladen.
3. **Ontologie-getriebene Avoid-Filter** — „ohne Schusswaffen", „kindgeeignet" → Hard-Filter auf `content_features`. „ohne Gewalt-Emotionen" → Score-Penalty.

## Zielgruppe der Software-Käufer

DACH-Streaming-Anbieter mit eigenem Katalog (3K-50K Filme), die ein USP-Feature für Onboarding/Discovery suchen und **kein** weiteres ML-Team aufbauen wollen.

## Aktuelles Korpus (Demo, Stand 2026-05-13)

- 15,255 Filme indiziert in Qdrant (Schema v2, vollständige Ontologie inkl. subjects/content_features)
- 21,411 Filme als Zielkorpus aus TMDB top-popularity vorbereitet
- Payload-Buckets `color_palette` + `protagonist_age` 2026-05-14 ergänzt — additiv, kein Reindex nötig (`scripts/payload_patch_color_age.py`)
