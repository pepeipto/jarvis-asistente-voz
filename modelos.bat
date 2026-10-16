@echo off
cd /d "%~dp0"
title Prueba de modelos de Jarvis
venv\Scripts\python.exe modelos.py %*
echo.
echo Listo. Resultado en modelos.txt. Esta ventana se cierra sola.
timeout /t 20 >nul
