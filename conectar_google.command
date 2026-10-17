#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -x venv/bin/python ]; then
  echo "Primero ejecuta instalar.command"
  read -r -p "Pulsa Intro para cerrar..." _
  exit 1
fi
echo "Conectar Jarvis con Google"
./venv/bin/python conectar_google.py
echo
read -r -p "Puedes cerrar esta ventana (Intro)..." _
