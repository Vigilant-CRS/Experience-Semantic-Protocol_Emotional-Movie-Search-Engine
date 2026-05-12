# MindRead — User Guide

**Was es kann:** Filme finden anhand dessen *was du fühlen willst*, nicht nur Genre/Schauspieler.

---

## Über das Web-UI

Öffne `http://localhost:8000/` (oder die URL deines Anbieters).

### 1. Such-Eingabe (oben)

Tippe was du suchst. Beispiele:

```
Filme wie John Wick aber lustiger
düstere Rachefilme mit Happy End
cyberpunk action ohne splatter
romantische Komödie zum Einschlafen
mind-bending Sci-Fi mit moralischem Dilemma
Filme wie Im Auftrag des Teufels
```

Das System versteht **Deutsch und Englisch**, erkennt Filmreferenzen, und filtert was du
ausschließen willst („ohne X").

### 2. Schieberegler (links)

Nach der ersten Suche siehst du im Wheel was der LLM extrahiert hat (gestrichelte Sektoren).
**Du kannst nachjustieren** ohne dass eine neue LLM-Anfrage geht — sehr schnell.

| Slider | Effekt |
|:--|:--|
| **Plot ↔ Theme** | Mehr Plot-Ähnlichkeit (Synopsis-Match) oder mehr thematische Ähnlichkeit |
| **Emotion-Anteil** | Wie sehr Emotionen das Ranking bestimmen sollen |
| **Indie ↔ Mainstream** | Bekannte Blockbuster oder versteckte Perlen |
| **Min Runtime** | Featurettes/Trailer ausfiltern (Default 60 min) |
| **Jahr ab** | Nur neuere Filme |

### 3. Wheel & Pills

- **Klick** auf Wheel-Sektor / Pill → Tag wird Teil deiner Suche
- **Shift+Klick** → Tag wird ausgeschlossen (avoid)
- **Wheel-Aussehen**:
  - 🟥 voll gefärbt = du hast es ausgewählt
  - ⚪ gestrichelt = LLM hat es vorgeschlagen
  - ⬛ dunkel mit rotem Rand = avoid

### 4. Streaming-Provider (links unten)

Klicke auf Provider-Pills um nur Filme zu zeigen, die du bei dem Dienst gucken kannst.
„Magenta TV+ (193)" heißt: 193 Filme im Index sind dort verfügbar.

### 5. Resultate (rechts)

Jede Karte zeigt:
- Poster + Titel + Jahr
- Genre · Archetype · Geschlecht der Hauptrolle · Runtime · ⭐ Bewertung · Votes
- 1-2 Zeilen Synopsis
- 🎭 / 📚 **Match-Tags** — *warum* dieser Film matched (hover für genauen Beitrag)
- Match-Score in % (relativ zum besten Treffer)
- "Wie dieser →" Button — Suche nach ähnlichen

### 6. Reset

Setzt Sliders, Wheel, Filter zurück. Tippt nicht den Suchtext.

---

## Tipps

- **Erst Free-Text, dann nachjustieren**: tippe lieber einen Satz statt nur Wheel zu klicken
- **„Wie dieser →"** ist mächtig: Such-Modus „ähnliche Filme" mit konkretem Referenzfilm
- **Avoid spart Re-Search**: kein Splatter? Tippe es einfach in die Query, oder Shift-Klick auf Wheel
- **Indie-Slider** nicht über 0.7 ziehen — sonst kommen nur extrem-Indie-Filme

---

## Häufige Fragen

**„Warum sehe ich nur ~7000 Filme statt 100K?"**
Aktueller Stand der Demo-DB. In Produktion wird der Provider seinen kompletten Katalog einliefern.

**„Warum dauert die erste Suche länger?"**
Erste Anfrage mit Free-Text → LLM-Call (~2-3 s). Slider-Tweaks danach sind <50 ms (kein LLM-Call mehr).

**„Was bedeuten die Channel-Scores wie `synopsis=0.83 emotion=0.19`?"**
Roh-Cosine-Score je Such-Channel. Über RRF-Fusion zusammengeführt zum Endrang.

**„Funktioniert das auf dem Smartphone?"**
Layout ist Desktop-First. Mobile-Layout ist Roadmap.
