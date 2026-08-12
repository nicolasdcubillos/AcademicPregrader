@echo off
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════════════════════
::  Academic Pregrader — Launcher
::  Modo Docker  : Java 21 + g++ incluidos, sin instalar nada extra
::  Modo local   : usa .venv de Python (requiere Java 21 y g++ instalados)
:: ═══════════════════════════════════════════════════════════════════════════════

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv\Scripts\python.exe"
set "FRONTEND=%ROOT%frontend\app.py"

echo.
echo  ============================================================
echo   Academic Pregrader
echo  ============================================================
echo.

:: ─── 1. Detectar Docker ───────────────────────────────────────────────────────
docker info >nul 2>&1
if !errorlevel! == 0 (
    echo  [OK] Docker detectado. Usando modo Docker ^(recomendado^).
    echo       Java 21, g++ y JPlag ya vienen incluidos.
    echo.
    goto :docker_mode
)

:: Docker no responde — ver si el binario existe pero el daemon no corre
where docker >nul 2>&1
if !errorlevel! == 0 (
    echo  [!] Docker esta instalado pero no esta corriendo.
    echo      Abre Docker Desktop y espera a que el icono de la barra
    echo      deje de girar, luego ejecuta este script de nuevo.
    echo.
    echo  Si prefieres continuar sin Docker ^(modo local^), presiona L.
    echo  Para salir, presiona cualquier otra tecla.
    echo.
    choice /c LS /n /m "  Opcion [L=Local / S=Salir]: "
    if !errorlevel! == 1 goto :local_mode
    exit /b 0
)

:: Docker no instalado
echo  [!] Docker Desktop NO esta instalado en este equipo.
echo.
echo  OPCIONES:
echo.
echo   [D] Instalar Docker Desktop ^(recomendado^)
echo       Descarga e instala Docker Desktop, luego vuelve a
echo       ejecutar este script. Con Docker no necesitas Java
echo       ni g++ — todo viene dentro del contenedor.
echo       URL: https://www.docker.com/products/docker-desktop
echo.
echo   [L] Continuar en modo local ^(sin Docker^)
echo       Requiere Python .venv, Java 21+ y g++ instalados.
echo.
echo   [S] Salir
echo.
choice /c DLS /n /m "  Opcion [D=Docker / L=Local / S=Salir]: "

if !errorlevel! == 1 (
    echo.
    echo  Abriendo pagina de descarga de Docker Desktop...
    start https://www.docker.com/products/docker-desktop
    echo.
    echo  Pasos:
    echo    1. Descarga e instala Docker Desktop
    echo    2. Reinicia el equipo si el instalador lo pide
    echo    3. Abre Docker Desktop y espera a que este listo
    echo    4. Ejecuta este script de nuevo
    echo.
    pause
    exit /b 0
)
if !errorlevel! == 2 goto :local_mode
exit /b 0


:: ═══════════════════════════════════════════════════════════════════════════════
:docker_mode
:: ═══════════════════════════════════════════════════════════════════════════════
echo  Iniciando con Docker Compose...
echo  La primera vez puede tardar unos minutos mientras descarga la imagen.
echo.

cd /d "%ROOT%"

:: Construir imagen si hay cambios, luego levantar
docker compose up --build -d >nul 2>&1
if !errorlevel! neq 0 (
    :: Intentar con docker-compose (v1) si falla docker compose (v2)
    docker-compose up --build -d >nul 2>&1
)

if !errorlevel! neq 0 (
    echo  [ERROR] No se pudo iniciar el contenedor.
    echo          Revisa que Docker Desktop este corriendo correctamente.
    pause
    exit /b 1
)

echo  [OK] Contenedor iniciado.
echo.
echo  ============================================================
echo   Abriendo http://localhost:5000 en tu navegador...
echo  ============================================================
echo.
echo  Para detener el servidor ejecuta:
echo    docker compose down
echo.

:: Dar un segundo para que Flask arranque dentro del contenedor
timeout /t 3 /nobreak >nul
start http://localhost:5000

echo  Presiona cualquier tecla para detener el servidor y salir.
pause >nul

echo.
echo  Deteniendo contenedor...
docker compose down >nul 2>&1
if !errorlevel! neq 0 docker-compose down >nul 2>&1
echo  Servidor detenido.
exit /b 0


:: ═══════════════════════════════════════════════════════════════════════════════
:local_mode
:: ═══════════════════════════════════════════════════════════════════════════════
echo.
echo  Usando modo local ^(sin Docker^).
echo.

:: Verificar entorno virtual Python
if not exist "%VENV%" (
    echo  [ERROR] No se encontro el entorno virtual en:
    echo          %VENV%
    echo.
    echo  Crea el entorno con estos comandos:
    echo    python -m venv .venv
    echo    .venv\Scripts\pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)

:: Advertencia sobre Java si JPlag esta habilitado
java -version >nul 2>&1
if !errorlevel! neq 0 (
    echo  [!] Java no encontrado en PATH.
    echo      La deteccion de plagio con JPlag no funcionara.
    echo      Instala Java 21+ desde: https://adoptium.net
    echo.
)

echo  ============================================================
echo   Iniciando servidor en http://127.0.0.1:5000
echo   Presiona Ctrl+C para detener.
echo  ============================================================
echo.

"%VENV%" "%FRONTEND%"

pause
