@echo off
cd /d "%~dp0"
title Conectar Jarvis con Google
venv\Scripts\python.exe conectar_google.py
echo.
echo Puedes cerrar esta ventana.
timeout /t 30 >nul
