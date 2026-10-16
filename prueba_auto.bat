@echo off
cd /d "%~dp0"
title Prueba automatica de Jarvis (silenciosa)
venv\Scripts\python.exe prueba_auto.py %*
echo.
echo Listo. Resultado en prueba_auto.txt. Esta ventana se cierra sola.
timeout /t 20 >nul
