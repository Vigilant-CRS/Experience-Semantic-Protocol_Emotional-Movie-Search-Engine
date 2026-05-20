@echo off
REM Vigilant ESP — Doppelklick-Start (Windows)
REM Startet Qdrant + API ueber docker-compose und oeffnet die UI.

cd /d "%~dp0"

echo ============================================================
echo  Vigilant ESP - Experience Semantic Protocol
echo  Engine codename: MindRead V3
echo ============================================================
echo.

REM 1) Docker pruefen
where docker >nul 2>nul
if errorlevel 1 (
    echo [X] Docker ist nicht installiert.
    echo     Installiere Docker Desktop von https://docker.com und versuche es erneut.
    pause
    exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
    echo [X] Docker laeuft nicht.
    echo     Bitte starte Docker Desktop und versuche es erneut.
    pause
    exit /b 1
)
echo [OK] Docker laeuft.

REM 2) .env pruefen
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [OK] .env aus .env.example angelegt.
        echo.
        echo WICHTIG: Bitte trage in .env deinen OPENAI_API_KEY ein.
        echo Pfad: %CD%\.env
        pause
    ) else (
        echo OPENAI_API_KEY=sk-PUT-YOUR-KEY-HERE > .env
        echo ADMIN_API_KEYS=admin-please-change-me >> .env
        echo OPENAI_MODEL_DNA=gpt-5-mini >> .env
        echo EMBEDDING_DEVICE=auto >> .env
        echo LOCAL_LLM_ENABLED=0 >> .env
        echo [!] .env wurde minimal angelegt - bitte OPENAI_API_KEY eintragen.
        pause
    )
)

REM 3) Container hochfahren
echo.
echo Starte Qdrant und Vigilant-ESP-API...
docker compose up -d
if errorlevel 1 (
    echo [X] docker compose fehlgeschlagen.
    pause
    exit /b 1
)

REM 4) Auf Gesundheit warten
echo.
echo Warte auf API (erstmaliger Start kann 2 Minuten dauern - E5-Modell wird geladen)...
set TIMEOUT=180
set ELAPSED=0
:wait_loop
curl -s -f http://localhost:8000/api/health >nul 2>nul
if not errorlevel 1 goto ready
timeout /t 3 /nobreak >nul
set /a ELAPSED+=3
if %ELAPSED% geq %TIMEOUT% (
    echo.
    echo [X] Timeout - API antwortet nach %TIMEOUT%s nicht.
    echo     Logs: docker compose logs api
    docker compose logs --tail 30 api
    pause
    exit /b 1
)
echo|set /p=.
goto wait_loop

:ready
echo  [OK]
echo.

REM 5) Browser oeffnen
start "" "http://localhost:8000/"

echo ============================================================
echo  [OK] Vigilant ESP laeuft auf http://localhost:8000/
echo.
echo    UI:     http://localhost:8000/
echo    API:    http://localhost:8000/api/docs   (Swagger)
echo    Health: http://localhost:8000/api/health
echo.
echo  Stoppen:  docker compose down
echo  (oder Fenster schliessen - Container laufen im Hintergrund weiter)
echo ============================================================
pause
