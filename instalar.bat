@echo off
setlocal
cd /d "%~dp0"
title Instalador de Jarvis
set "LOG=%~dp0instalar_log.txt"
set "VPY=%~dp0venv\Scripts\python.exe"
echo Instalacion iniciada el %date% a las %time% > "%LOG%"

echo ==============================================
echo   INSTALADOR DE JARVIS
echo ==============================================
echo.
echo IMPORTANTE: cierra cualquier otra ventana negra de Jarvis antes de continuar.
echo.

set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY goto nopython

echo Python encontrado:
%PY% --version
%PY% --version >> "%LOG%" 2>&1
echo.

set "NEEDVENV=0"
if not exist "%VPY%" set "NEEDVENV=1"
if exist "%VPY%" (
  "%VPY%" -c "import sys" >nul 2>&1 || set "NEEDVENV=1"
)
if "%NEEDVENV%"=="1" (
  if exist venv rmdir /s /q venv
  if exist venv goto bloqueado
  echo Creando entorno...
  %PY% -m venv venv >> "%LOG%" 2>&1
  if errorlevel 1 goto errvenv
)

set "PIPOPT=--disable-pip-version-check --no-input"
echo [1/3] Instalando paquetes basicos. Tarda de 1 a 4 minutos, no cierres la ventana...
"%VPY%" -m pip install %PIPOPT% anthropic requests python-dotenv numpy pypdf python-docx websocket-client google-api-python-client google-auth-oauthlib >> "%LOG%" 2>&1
if errorlevel 1 (
  echo       Ha fallado. Reintentando una vez...
  "%VPY%" -m pip install %PIPOPT% --no-cache-dir anthropic requests python-dotenv numpy pypdf python-docx websocket-client google-api-python-client google-auth-oauthlib >> "%LOG%" 2>&1
  if errorlevel 1 goto errpip
)
echo       OK
echo.
echo [2/3] Instalando audio...
"%VPY%" -m pip install %PIPOPT% sounddevice >> "%LOG%" 2>&1
if errorlevel 1 (
  echo       AVISO: no se pudo instalar el audio. Podras escribir a Jarvis pero no hablarle.
) else (
  echo       OK
)

echo.
echo [3/3] Comprobando Ollama, la IA gratuita que funciona en tu PC...
where ollama >nul 2>&1
if errorlevel 1 (
  echo       Ollama no esta instalado.
  echo       Descargalo de https://ollama.com/download , instalalo y vuelve a ejecutar este archivo.
  goto finollama
)
set "MODELO=granite4.1:8b"
set "TAMANO=5.3 GB"
set "VRAM=0"
for /f "tokens=1" %%M in ('nvidia-smi --query-gpu^=memory.total --format^=csv^,noheader^,nounits 2^>nul') do set "VRAM=%%M"
if %VRAM% GEQ 20000 (
  set "MODELO=qwen3.8:27b"
  set "TAMANO=18 GB"
)
if not "%VRAM%"=="0" echo       Tarjeta grafica con %VRAM% MB: el modelo recomendado es %MODELO%.
ollama list > "%TEMP%\jarvis_ollama.txt" 2>&1
findstr /i /c:"%MODELO%" "%TEMP%\jarvis_ollama.txt" >nul
if not errorlevel 1 (
  echo       OK: %MODELO% ya esta descargado.
  goto finollama
)
choice /c SN /m "      Descargar ahora %MODELO%, unos %TAMANO%"
if errorlevel 2 goto finollama
ollama pull %MODELO%
if errorlevel 1 echo       No se pudo descargar. Abre la aplicacion Ollama y vuelve a ejecutar este archivo.
:finollama

if not exist .env copy .env.example .env >nul

echo.
echo ==============================================
echo   RESULTADO
echo ==============================================
"%VPY%" -c "import anthropic, numpy, requests, dotenv, pypdf, docx; print('Escritura y cerebro ... OK')" 2>>"%LOG%" || echo Escritura y cerebro ... FALLA
"%VPY%" -c "import sounddevice, numpy; print('Voz y microfono ....... OK')" 2>>"%LOG%" || echo Voz y microfono ....... FALLA
where ollama >nul 2>&1 && echo IA local Ollama ........ OK || echo IA local Ollama ........ NO INSTALADA
echo.
echo Siguiente paso: abre el archivo .env con el Bloc de notas y pon tus claves.
echo Despues haz doble clic en jarvis.bat
echo Los detalles tecnicos estan en instalar_log.txt
echo.
pause
exit /b 0

:nopython
echo ERROR: no se encuentra Python.
echo Instala Python 3.12 desde https://www.python.org/downloads/
echo y marca la casilla "Add python.exe to PATH" durante la instalacion.
echo Despues vuelve a ejecutar este archivo.
pause
exit /b 1

:bloqueado
echo ERROR: no se pudo borrar la carpeta venv porque algun programa la esta usando.
echo Cierra TODAS las ventanas negras de Jarvis y vuelve a ejecutar este archivo.
pause
exit /b 1

:errvenv
echo ERROR: no se pudo crear el entorno. Ultimas lineas del registro:
powershell -NoProfile -Command "Get-Content -Tail 20 -LiteralPath '%LOG%'"
echo.
echo Haz una captura de esta ventana y enviamela.
pause
exit /b 1

:errpip
echo ERROR: fallo la instalacion de paquetes. Ultimas lineas del registro:
powershell -NoProfile -Command "Get-Content -Tail 20 -LiteralPath '%LOG%'"
echo.
echo Si ves "Access is denied" o "Acceso denegado", pausa un momento el antivirus y repite.
echo Haz una captura de esta ventana y enviamela.
pause
exit /b 1
