# Vigilant ESP — Schnellstart

**Doppelklick und los.** Du brauchst nur Docker Desktop installiert.

---

## In 3 Schritten zum Laufen

### 1. Docker Desktop installieren (einmalig)

Falls noch nicht da: [docker.com](https://www.docker.com/products/docker-desktop) → herunterladen, installieren, starten.

### 2. OpenAI-API-Key in `.env` eintragen (einmalig)

Beim ersten Doppelklick auf `start.sh` (Linux/Mac) bzw. `start.bat` (Windows) wird automatisch eine `.env`-Datei angelegt. Öffne sie in einem Editor und ersetze die Platzhalter:

```env
OPENAI_API_KEY=sk-dein-echter-key
ADMIN_API_KEYS=ein-zufaelliger-langer-string
```

OpenAI-Key holst du dir auf [platform.openai.com](https://platform.openai.com).

### 3. Doppelklick starten

| Dein OS | Datei zum Doppelklick |
|---|---|
| **Linux** | `start.sh` *oder* `Vigilant-ESP.desktop` |
| **Windows** | `start.bat` |
| **macOS** | `start.sh` (Rechtsklick → „Öffnen mit Terminal") |

Der Browser öffnet sich nach 30 s – 2 min automatisch auf `http://localhost:8000/`. Beim allerersten Start dauert es bis zu **5 Minuten**, weil das Embedding-Modell (1.3 GB) heruntergeladen wird. Beim zweiten Start sind es <30 s.

---

## Was passiert genau

Das Start-Skript macht der Reihe nach:

1. **prüft** ob Docker installiert ist und läuft
2. **legt `.env` an** falls noch nicht vorhanden
3. **`docker compose up -d`** — startet Qdrant (Vektor-DB) + Vigilant-ESP-API
4. **wartet** bis `http://localhost:8000/api/health` „healthy" zurückgibt
5. **öffnet** den Browser auf der UI

---

## Wenn was schiefläuft

| Symptom | Was tun |
|---|---|
| „Docker ist nicht installiert" | [Docker Desktop herunterladen](https://www.docker.com/products/docker-desktop) |
| „Docker läuft nicht" | Docker Desktop App öffnen und auf den Walen warten (✓ in Statusleiste) |
| Timeout nach 3 min | `docker compose logs api` im Terminal — meist OPENAI_API_KEY falsch |
| Browser öffnet sich nicht | Manuell `http://localhost:8000/` aufrufen |
| Port 8000 belegt | `docker compose down` und `lsof -i :8000` checken |

---

## Stoppen

Einfach das Fenster schließen — die Container laufen im Hintergrund weiter und sind beim nächsten Doppelklick sofort wieder aktiv.

Komplett stoppen:
```bash
docker compose down
```

Komplett löschen (inkl. Qdrant-Daten):
```bash
docker compose down -v
```

---

## Daten reinkippen

Die Demo läuft out-of-the-box mit 15.255 vorindexierten Filmen. Wenn du dein eigenes Verzeichnis einkippen willst:

```bash
curl -X POST http://localhost:8000/api/admin/films/csv \
     -H 'X-API-Key: dein-admin-key-aus-.env' \
     -F 'file=@dein-katalog.csv'
```

Format-Details: [docs/API_GUIDE.md](docs/API_GUIDE.md), Schritt-für-Schritt: [INSTALL.md](INSTALL.md).

---

## Was wo zu finden ist

| Datei / URL | Was |
|---|---|
| `http://localhost:8000/` | Such-UI (Wheel + Mix-Bar) |
| `http://localhost:8000/api/docs` | API-Doku (Swagger, interaktiv) |
| `http://localhost:8000/api/health` | Status + Index-Stats |
| `start.sh` / `start.bat` | Doppelklick-Launcher |
| `.env.example` | Konfigurations-Template |
| `INSTALL.md` | Vollständiges Onboarding |
| `docs/API_GUIDE.md` | API-Referenz |
| `docs/USER_GUIDE.md` | End-User Guide |
| `docs/ARCHITECTURE.md` | Architektur-Übersicht |
| `LICENSE` | Proprietäre Software-Lizenz |
| `THIRD_PARTY_NOTICES.md` | OSS-Komponenten-Attribution |
