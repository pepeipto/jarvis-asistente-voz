#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -x venv/bin/python ]; then
  echo "Primero ejecuta instalar.command"
  read -r -p "Pulsa Intro para cerrar..." _
  exit 1
fi
echo "Actualizando paquetes de Jarvis..."
if ./venv/bin/python -m pip install --disable-pip-version-check --no-input -r requirements.txt > actualizar_log.txt 2>&1; then
  echo OK
else
  echo "FALLO: mira actualizar_log.txt"
fi
echo fin >> actualizar_log.txt
sleep 5
