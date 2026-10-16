@echo off
cd /d "%~dp0"
title Diagnostico de Jarvis
if not exist venv\Scripts\python.exe (
  echo Primero ejecuta instalar.bat > diagnostico.txt
  exit /b 1
)
venv\Scripts\python.exe diagnostico.py
echo.
echo Listo. Resultado en diagnostico.txt. Esta ventana se cierra sola.
timeout /t 20 >nul
