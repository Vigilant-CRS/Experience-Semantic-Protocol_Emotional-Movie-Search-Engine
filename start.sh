#!/usr/bin/env bash
# Vigilant ESP — Doppelklick-Start
# Startet Qdrant + API über docker-compose und öffnet die UI im Browser.
# Erstmaliger Start dauert 3-5 Minuten (Image-Build), danach <30 s.

set -e

cd "$(dirname "$0")"

echo "════════════════════════════════════════════════════════════"
echo "  Vigilant ESP — Experience Semantic Protocol"
echo "  Engine codename: MindRead V3"
echo "════════════════════════════════════════════════════════════"
echo

# ── 1) Docker prüfen ────────────────────────────────────────────────
if ! command -v docker > /dev/null 2>&1; then
    echo "❌ Docker ist nicht installiert."
    echo "   Installiere Docker Desktop von https://docker.com und versuche es erneut."
    read -p "Drücke Enter um das Fenster zu schließen…"
    exit 1
fi
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker läuft nicht."
    echo "   Bitte starte Docker Desktop und versuche es erneut."
    read -p "Drücke Enter um das Fenster zu schließen…"
    exit 1
fi
echo "✓ Docker läuft."

# ── 2) .env existiert? ──────────────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✓ .env aus .env.example angelegt."
        echo
        echo "⚠️  WICHTIG: Bitte trage in die Datei .env deinen OPENAI_API_KEY ein."
        echo "   Datei-Pfad: $(pwd)/.env"
        echo
        read -p "Drücke Enter wenn du .env bearbeitet hast (oder strg+c zum Abbrechen)…"
    else
        echo "⚠️  Keine .env oder .env.example gefunden. Erzeuge minimale .env…"
        cat > .env <<'EOF'
OPENAI_API_KEY=sk-PUT-YOUR-KEY-HERE
ADMIN_API_KEYS=admin-please-change-me
OPENAI_MODEL_DNA=gpt-5-mini
EMBEDDING_DEVICE=auto
LOCAL_LLM_ENABLED=0
EOF
        echo "   $(pwd)/.env wurde angelegt — bitte OPENAI_API_KEY eintragen."
        read -p "Drücke Enter wenn fertig…"
    fi
fi

# ── 3) Container hochfahren ─────────────────────────────────────────
echo
echo "🚀 Starte Qdrant und Vigilant-ESP-API…"
docker compose up -d

# ── 4) Auf Gesundheit warten ───────────────────────────────────────
echo
echo "⏳ Warte auf API (kann beim ersten Start bis zu 2 Minuten dauern,"
echo "   da E5-Modell heruntergeladen wird)…"
TIMEOUT=180
ELAPSED=0
while ! curl -s -f http://localhost:8000/api/health > /dev/null 2>&1; do
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "❌ Timeout — API antwortet nicht nach $TIMEOUT s."
        echo "   Logs: docker compose logs api"
        read -p "Drücke Enter um Logs zu sehen, dann Enter zum Schließen…"
        docker compose logs --tail 30 api
        read -p "Enter zum Schließen…"
        exit 1
    fi
    printf "."
done
echo " ✓"
echo

# ── 5) Browser öffnen ───────────────────────────────────────────────
URL="http://localhost:8000/"
echo "🌐 Öffne $URL im Browser…"
if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "$URL" > /dev/null 2>&1 &
elif command -v open > /dev/null 2>&1; then
    open "$URL"
elif command -v start > /dev/null 2>&1; then
    start "$URL"
else
    echo "   (Browser konnte nicht automatisch geöffnet werden — bitte $URL manuell aufrufen.)"
fi

echo
echo "════════════════════════════════════════════════════════════"
echo "  ✓ Vigilant ESP läuft auf http://localhost:8000/"
echo
echo "    UI:     http://localhost:8000/"
echo "    API:    http://localhost:8000/api/docs   (Swagger)"
echo "    Health: http://localhost:8000/api/health"
echo
echo "  Stoppen mit:  docker compose down"
echo "  (oder schließe das Fenster — Container laufen im Hintergrund weiter)"
echo "════════════════════════════════════════════════════════════"
read -p "Drücke Enter um dieses Fenster zu schließen…"
