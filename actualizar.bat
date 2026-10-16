@echo off
cd /d "%~dp0"
title Actualizar Jarvis
echo Actualizando paquetes de Jarvis...
venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-input -r requirements.txt > actualizar_log.txt 2>&1
if errorlevel 1 (echo FALLO: mira actualizar_log.txt) else (echo OK)
echo fin >> actualizar_log.txt
timeout /t 10 >nul
