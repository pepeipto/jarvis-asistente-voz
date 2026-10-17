#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -x venv/bin/python ]; then
  echo "Primero ejecuta instalar.command"
  read -r -p "Pulsa Intro para cerrar..." _
  exit 1
fi
./venv/bin/python jarvis.py
read -r -p "Pulsa Intro para cerrar..." _
