#!/bin/bash
# Instalador de Jarvis para macOS (equivalente a instalar.bat)
cd "$(dirname "$0")" || exit 1
LOG="$PWD/instalar_log.txt"
VPY="$PWD/venv/bin/python"
echo "Instalacion iniciada el $(date)" > "$LOG"

echo "=============================================="
echo "  INSTALADOR DE JARVIS (macOS)"
echo "=============================================="
echo
echo "IMPORTANTE: cierra cualquier otra ventana de Terminal con Jarvis antes de continuar."
echo

# Hacer ejecutables el resto de scripts
chmod +x ./*.command 2>/dev/null

# --- Python 3.10 - 3.13
PY=""
for v in 3.12 3.11 3.13 3.10; do
  if command -v "python$v" >/dev/null 2>&1; then PY="python$v"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then PY="python3"; fi
fi
if [ -z "$PY" ]; then
  echo "ERROR: no encuentro Python 3.10 - 3.13."
  echo "Instalalo con Homebrew:   brew install python@3.12"
  echo "(Homebrew: https://brew.sh)  o desde https://www.python.org/downloads/"
  echo "Despues vuelve a ejecutar este archivo."
  read -r -p "Pulsa Intro para cerrar..." _
  exit 1
fi
echo "Python encontrado: $($PY --version)"
$PY --version >> "$LOG" 2>&1
echo

# --- entorno virtual
NEEDVENV=0
[ -x "$VPY" ] || NEEDVENV=1
if [ "$NEEDVENV" = "0" ] && ! "$VPY" -c "import sys" >/dev/null 2>&1; then NEEDVENV=1; fi
if [ "$NEEDVENV" = "1" ]; then
  rm -rf venv
  echo "Creando entorno..."
  if ! $PY -m venv venv >> "$LOG" 2>&1; then
    echo "ERROR: no se pudo crear el entorno. Ultimas lineas del registro:"
    tail -n 20 "$LOG"
    read -r -p "Pulsa Intro para cerrar..." _
    exit 1
  fi
fi

PIPOPT="--disable-pip-version-check --no-input"
echo "[1/3] Instalando paquetes basicos. Tarda de 1 a 4 minutos, no cierres la ventana..."
BASICOS="anthropic requests python-dotenv numpy pypdf python-docx websocket-client google-api-python-client google-auth-oauthlib"
if ! "$VPY" -m pip install $PIPOPT $BASICOS >> "$LOG" 2>&1; then
  echo "      Ha fallado. Reintentando una vez..."
  if ! "$VPY" -m pip install $PIPOPT --no-cache-dir $BASICOS >> "$LOG" 2>&1; then
    echo "ERROR: fallo la instalacion de paquetes. Ultimas lineas del registro:"
    tail -n 20 "$LOG"
    read -r -p "Pulsa Intro para cerrar..." _
    exit 1
  fi
fi
echo "      OK"
echo
echo "[2/3] Instalando audio..."
if "$VPY" -m pip install $PIPOPT sounddevice >> "$LOG" 2>&1; then
  echo "      OK"
else
  echo "      AVISO: no se pudo instalar el audio. Podras escribir a Jarvis pero no hablarle."
fi

# --- Ollama
echo
echo "[3/3] Comprobando Ollama, la IA gratuita que funciona en tu Mac..."
# Si en .env o ajustes.env hay OLLAMA_URL, el cerebro esta en otro equipo y no hace falta Ollama aqui.
REMOTO=""
for f in .env ajustes.env; do
  [ -f "$f" ] && REMOTO=$(grep -E '^OLLAMA_URL=.+' "$f" | head -n1 | cut -d= -f2-)
  [ -n "$REMOTO" ] && break
done
if [ -n "$REMOTO" ]; then
  echo "      OLLAMA_URL = $REMOTO (cerebro en otro equipo): no hace falta instalar Ollama aqui."
elif ! command -v ollama >/dev/null 2>&1 && [ ! -x /Applications/Ollama.app/Contents/Resources/ollama ]; then
  echo "      Ollama no esta instalado."
  echo "      Descargalo de https://ollama.com/download (o: brew install --cask ollama), abrelo"
  echo "      y vuelve a ejecutar este archivo."
else
  OLLAMA=$(command -v ollama || echo /Applications/Ollama.app/Contents/Resources/ollama)
  MODELO="granite4.1:8b"; TAMANO="5.3 GB"
  MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
  if [ "$MEM_GB" -ge 32 ]; then MODELO="qwen3.8:27b"; TAMANO="18 GB"; fi
  [ "$MEM_GB" -gt 0 ] && echo "      Memoria del Mac: ${MEM_GB} GB: el modelo recomendado es $MODELO."
  if "$OLLAMA" list 2>/dev/null | grep -qi "$MODELO"; then
    echo "      OK: $MODELO ya esta descargado."
  else
    read -r -p "      Descargar ahora $MODELO, unos $TAMANO (s/n)? " R
    if [[ "$R" =~ ^[sSyY]$ ]]; then
      "$OLLAMA" pull "$MODELO" || echo "      No se pudo descargar. Abre la aplicacion Ollama y vuelve a ejecutar este archivo."
    fi
  fi
fi

[ -f .env ] || cp .env.example .env

echo
echo "=============================================="
echo "  RESULTADO"
echo "=============================================="
"$VPY" -c "import anthropic, numpy, requests, dotenv, pypdf, docx; print('Escritura y cerebro ... OK')" 2>>"$LOG" || echo "Escritura y cerebro ... FALLA"
"$VPY" -c "import sounddevice, numpy; print('Voz y microfono ....... OK')" 2>>"$LOG" || echo "Voz y microfono ....... FALLA"
if command -v ollama >/dev/null 2>&1 || [ -x /Applications/Ollama.app/Contents/Resources/ollama ]; then
  echo "IA local Ollama ........ OK"
else
  echo "IA local Ollama ........ NO INSTALADA (o usa OLLAMA_URL con otro equipo)"
fi
echo
echo "Siguiente paso: abre el archivo .env con TextEdit (open -e .env) y pon tus claves."
echo "Despues haz doble clic en jarvis.command"
echo "La primera vez macOS pedira permiso de MICROFONO para Terminal: pulsa Permitir."
echo "Los detalles tecnicos estan en instalar_log.txt"
echo
read -r -p "Pulsa Intro para cerrar..." _
