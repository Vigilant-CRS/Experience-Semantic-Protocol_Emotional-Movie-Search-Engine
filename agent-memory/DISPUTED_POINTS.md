# Disputed Points

Offene Design- und Strategie-Fragen. Nicht „Bugs", sondern echte Trade-offs ohne klare Antwort.

## DP-001 Subjects mit eigenem Slider oder Teil von Theme?

**Frage:** Soll `subjects` einen eigenen Sparse-Vektor + eigenen Slider („Subjects-Anteil") bekommen, oder als Sub-Bucket in theme_sparse bleiben?

**Pro eigener Slider:**
- User mit Subject-Query („Vampirfilme") will klares Subject-Ranking, nicht verwässert durch Theme-Tags
- Klarere Separation in UI

**Contra:**
- 4-Slider-UI komplexer
- Subjects sind in 24 Tags relativ klein — eigener Vektor wirkt schwach
- Aktueller Stand: Subjects funktionieren ausreichend in theme_sparse mit theme-Slider

**Status:** offen. Vertagt bis nach B2B-MVP.

## DP-002 Re-Extract der alten 7K — ja oder nein?

**Frage:** Sollen wir die 7K alten Filme (extracted via gpt-5-mini ohne subjects/content_features) re-extracten?

**Pro:**
- Konsistentes Korpus
- „John Wick ohne Schusswaffen" und „Vampirfilme" würden voll funktionieren
- Kostet nur $9, dauert <1h

**Contra:**
- Working set ist fertig getestet, neuer Run bringt Variance
- Kann auch progressiv geschehen wenn Käufer ohnehin reindexiert

**Status:** offen. Empfehlung: ja, weil B2B-Demo davon profitiert.

## DP-003 Local Qwen für Runtime — abschalten oder ausbauen?

**Frage:** Sollen wir den `LOCAL_LLM_ENABLED` Pfad für Live-Queries aufrechterhalten?

**Pro abschalten:**
- 40-60s/Query auf Quadro P620 → für Demo unbenutzbar
- llm_local.py ist nicht synchron mit api_v3.py Prompts (fehlt subjects, content_features, gender, year)
- Wartungskosten ohne Nutzen

**Pro ausbauen:**
- B2B-Käufer mit eigenem GPU-Server (RTX 4090 oder besser) braucht keinen OpenAI-Account
- Argument „komplett lokal, keine API-Abhängigkeit" verkauft sich gut

**Status:** offen. Aktuell pragmatisch: Code bleibt, ist deaktiviert. Wenn Käufer-Anfrage kommt → llm_local.py auf Stand bringen.

## DP-004 Sollen LGBTQ/Identitäts-Themen ins Ontologie-Set?

**Frage:** Tags wie `lgbtq_protagonist`, `coming_out`, `racial_identity`, `immigrant_story` hinzufügen?

**Pro:**
- Echte User-Suchqueries („queer love story", „films about immigration")
- v1 hatte LGBTQ-related Tags
- Editorial-Wert für Demo („Diversity-suchen-möglich")

**Contra:**
- Politisch sensibler Bereich, brauche User-Approval
- LLM-Mis-tagging kann beleidigend wirken
- Bucket-Zugehörigkeit unklar (theme? subject? archetype?)

**Status:** offen. User-Entscheidung erforderlich.

## DP-005 Subject-Tag Konservativität — was bedeutet „prominent"?

**Frage:** Wann setzt der LLM `subjects.mafia = 1.0`? Bei jedem Film mit einer Mob-Szene? Nur wenn die ganze Story um Mafia geht?

**Aktuelle Anweisung im Prompt:** „only set when CENTRAL to the film" — schwammig.

**Beispiel-Streitfall:**
- „The Departed" — clearly mafia-zentriert ✓
- „Lethal Weapon 2" — South-African Drogenring, mob-adjacent ?
- „Pulp Fiction" — Mob-Hintergrund, aber Story um Charaktere, nicht Mob ?

**Konsequenz:** Inkonsistente Subject-Tagging → schwacher Match-Score.

**Lösungsansatz:** Few-Shot-Beispiele im Prompt mit Grenzfällen + Weight-Stufen (1.0 zentral, 0.6 prominent, 0.3 peripher).

**Status:** offen, niedrige Priorität.

## DP-006 Eval-Tests vs Engine-Tuning — Henne/Ei

**Frage:** Wir haben die Eval-Tests mehrfach erweitert weil Engine-Output „semantisch valide aber nicht in Liste" war. Ab wann ist das Test-Gaming statt Test-Realismus?

**Beispiel:** `edge_amelie_more_action` returnte Ballerina, Kung Fu Dunk → wir nahmen die in die Erwartungsliste auf. Damit testen wir nicht mehr ob „Filme wie Amélie aber mit mehr Action" funktioniert, sondern ob wir die gleichen Filme wiederfinden.

**Lösungsansatz:** Eval-Tests sollten **Eigenschaften** prüfen, nicht **konkrete Filme**. Z.B. „mindestens 2 Filme im Top-10 haben subjects.action_packed > 0 UND archetype != Drama".

**Status:** offen, würde Eval-Suite überarbeiten.

## DP-007 Wie ehrlich/transparent das System in der UI sein?

**Frage:** Soll die UI zeigen:
- Welche Tags der LLM extrahiert hat? (aktuell ja, im „Intent" Panel)
- Welcher LLM gerade aktiv ist? (User wollte: NEIN, gerade entfernt)
- Welche Filter-Aktionen passieren? („Wir filtern firearms raus")
- Confidence-Scores pro Match?

**Trade-off:** Mehr Transparenz = mehr Vertrauen, aber auch mehr Komplexität.

**Status:** Iterativ. User-Feedback steuert.

## DP-008 Tone-Shift-Blend adaptive machen?

**Frage:** Aktuell hart-kodiertes 60/40. Sollte adaptiv sein, basierend auf Modifier-Stärke?

**Idee:** Wenn LLM 5 Modifier-Tags mit Total-Weight 2.0 extrahiert → Modifier dominant → 40/60 oder 30/70. Wenn nur 1 schwacher Tag → 70/30.

**Risiko:** Mehr Komplexität, schwerer zu debuggen, schwerer dem User zu erklären.

**Status:** offen, niedrige Priorität.
