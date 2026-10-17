"""
OmniRoute: el proxy local por el que Jarvis habla con Claude (ANTHROPIC_BASE_URL=http://localhost:20128).

Si el cerebro va por OmniRoute y esta cerrado, Jarvis lo abre al arrancar (sin ventana) y espera a que
acepte conexiones. Al salir cierra solo el OmniRoute que abrio el (nunca uno que ya estuviera abierto).
"""
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

LOG = Path(__file__).resolve().with_name("omniroute_log.txt")
ESPERA = 60                      # segundos maximos esperando a que OmniRoute acepte conexiones
_proc = None                     # el OmniRoute que ha lanzado Jarvis
_esperar = time.sleep            # sustituible en las pruebas


def _url():
    return urlparse(os.environ.get("ANTHROPIC_BASE_URL", "").strip())


def configurado():
    """True si el cerebro va por un OmniRoute en este PC (URL local y token)."""
    u = _url()
    return (u.hostname or "") in ("localhost", "127.0.0.1") and bool(os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def responde():
    """True si el puerto de OmniRoute acepta conexiones (medio segundo como mucho)."""
    u = _url()
    try:
        with socket.create_connection((u.hostname or "localhost", u.port or 20128), timeout=0.5):
            return True
    except OSError:
        return False


def buscar():
    """Ruta del lanzador de OmniRoute (instalado con npm), o None."""
    ruta = shutil.which("omniroute.cmd") or shutil.which("omniroute")
    if ruta:
        return ruta
    npm = Path(os.path.expandvars(r"%APPDATA%\npm\omniroute.cmd"))
    return str(npm) if npm.is_file() else None


def _matar(proc):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def iniciar(espera=ESPERA):
    """Abre OmniRoute si hace falta. None si queda listo (o no se usa); si no, el problema en una frase."""
    global _proc
    if not configurado() or responde():
        return None
    exe = buscar()
    if not exe:
        return "OmniRoute está cerrado y no lo encuentro instalado; uso el cerebro local."
    try:
        with open(LOG, "ab") as log:
            _proc = subprocess.Popen(["cmd", "/c", exe], stdout=log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as e:
        _proc = None
        return f"No he podido abrir OmniRoute ({e}); uso el cerebro local."
    fin = time.time() + espera
    while time.time() < fin:
        if responde():
            return None
        if _proc.poll() is not None:
            _proc = None
            return "OmniRoute se ha cerrado al arrancar; mira omniroute_log.txt. Uso el cerebro local."
        _esperar(1)
    return f"OmniRoute no ha respondido en {espera} s; uso el cerebro local mientras tanto."


def parar():
    """Cierra solo el OmniRoute que abrio Jarvis."""
    global _proc
    proc, _proc = _proc, None
    if proc is not None:
        try:
            _matar(proc)
        except Exception:
            pass
