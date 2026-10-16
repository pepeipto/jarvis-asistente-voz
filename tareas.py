"""
Tareas grandes: Jarvis se las encarga a Claude Code (modo no interactivo) en segundo plano.

Seguridad:
- Nada se ejecuta sin confirmacion: encargar_tarea solo deja la tarea pendiente y Jarvis la repite.
  La confirmacion ("si", "adelante"...) la comprueba este codigo en la siguiente frase del usuario,
  no la IA (jarvis.responder llama a respuesta_confirmacion antes de preguntar a la IA).
- Tras leer contenido externo (correos, archivos, web) durante 180 s no se aceptan encargos: un texto
  malicioso podria intentar que la IA encargue algo que el usuario no ha pedido.
- Claude Code solo puede usar las herramientas de PERMITIDAS (sin consola libre). En modo -p lo demas
  se deniega solo. La carpeta de trabajo debe estar dentro de las carpetas permitidas (pc.py).
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pc

PERMITIDAS = ["Read", "Glob", "Grep", "Edit", "Write", "WebSearch", "WebFetch",
              "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)"]
MODELO = os.environ.get("MODELO_TAREAS") or "cc/claude-sonnet-5-5"
TIEMPO_MAXIMO = 15 * 60         # segundos
CADUCA_PENDIENTE = 120          # segundos para confirmar
BLOQUEO_EXTERNO = 180           # segundos sin encargos tras leer contenido externo
CARPETA_DEFECTO = pc._carpeta_conocida("documentos") / "Jarvis" / "tareas"
LOG = Path(__file__).resolve().with_name("tareas_log.txt")

_SI = re.compile(r"^(s[ií]|adelante|vale|hazlo|confirmo|confirmado|de acuerdo|ok|okey|venga|claro|dale|empieza)\b")
_NO = re.compile(r"^(no|cancela\w*|espera|para|d[eé]jalo|olv[ií]dalo|mejor no)\b")

_pendiente = None               # {"descripcion", "carpeta", "momento"}
_actual = None                  # {"descripcion", "carpeta", "inicio", "proceso"}
_ultimo_externo = 0.0
_cerrojo = threading.Lock()
on_fin = None                   # funcion(texto) para avisar al usuario cuando termina una tarea


def marcar_contenido_externo():
    """Llamar cada vez que la IA lee correos, archivos o la web."""
    global _ultimo_externo
    _ultimo_externo = time.time()


def pendiente():
    global _pendiente
    if _pendiente and time.time() - _pendiente["momento"] > CADUCA_PENDIENTE:
        _pendiente = None
    return _pendiente


def ejecutable():
    """claude.exe nativo (no claude.cmd: asi el texto de la tarea no pasa por la consola de Windows)."""
    candidatos = [Path(os.path.expandvars(r"%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")),
                  Path.home() / ".local" / "bin" / "claude.exe"]
    for c in candidatos:
        if c.exists() and c.stat().st_size > 1_000_000:
            return str(c)
    return shutil.which("claude.exe")


def comando(descripcion, carpeta):
    instrucciones = (f"{descripcion}\n\nTrabajas en la carpeta {carpeta}. No borres archivos salvo que la tarea lo "
                     "pida expresamente. Al terminar, resume en una o dos frases en español, para leerlas en voz "
                     "alta, lo que has hecho.")
    return [ejecutable() or "claude.exe", "-p", instrucciones, "--output-format", "json",
            "--model", MODELO, "--allowedTools", *PERMITIDAS]


def _entorno():
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)        # con OmniRoute solo se usa el token
    env.pop("CLAUDECODE", None)
    return env


def _avisar(texto):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%d/%m/%Y %H:%M')} {texto}\n")
    if on_fin:
        on_fin(texto)


def _trabajar(descripcion, carpeta):
    global _actual
    salida = ""
    try:
        proc = subprocess.Popen(comando(descripcion, carpeta), cwd=str(carpeta), env=_entorno(),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _actual["proceso"] = proc
        try:
            salida, _ = proc.communicate(timeout=TIEMPO_MAXIMO)
        except subprocess.TimeoutExpired:
            _matar(proc)
            _avisar(f"La tarea «{descripcion}» tardaba más de {TIEMPO_MAXIMO // 60} minutos y la he parado.")
            return
        salida = (salida or b"").decode("utf-8", errors="replace")
        if _actual.get("cancelada"):
            return
        try:
            datos = json.loads(salida.strip().splitlines()[-1])
            texto = (datos.get("result") or "").strip()
            fallo = datos.get("is_error") or proc.returncode != 0
        except (ValueError, IndexError):
            texto, fallo = salida.strip()[-300:], True
        if fallo:
            _avisar(f"La tarea «{descripcion}» ha fallado: {texto[:300] or 'sin detalle'}")
        else:
            _avisar(f"Tarea terminada. {texto[:600]}")
    except OSError as e:
        _avisar(f"No he podido abrir Claude Code: {e}")
    finally:
        with _cerrojo:
            _actual = None


def _matar(proc):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _lanzar(descripcion, carpeta):
    global _actual
    with _cerrojo:
        _actual = {"descripcion": descripcion, "carpeta": carpeta, "inicio": time.time(), "proceso": None}
    threading.Thread(target=_trabajar, args=(descripcion, carpeta), daemon=True, name="tarea").start()


def respuesta_confirmacion(texto):
    """Si hay una tarea esperando confirmacion, decide con la frase del usuario.
    Devuelve el texto a decir, o None si no hay nada pendiente (o la frase es otra peticion)."""
    global _pendiente
    p = pendiente()
    if not p:
        return None
    t = pc._norm(texto)
    t = re.sub(r"^(oye |eh )?(jarvis|carvis|yarvis|jarbis)[\s,.:;!¡¿?]*", "", t).strip(" ,.!¡¿?")
    _pendiente = None
    if _SI.match(t):
        if not ejecutable():
            return "No encuentro Claude Code instalado. Instálalo con: npm install -g @anthropic-ai/claude-code"
        _lanzar(p["descripcion"], p["carpeta"])
        return "Me pongo con ello. Te aviso cuando termine."
    if _NO.match(t):
        return "Vale, no hago nada."
    return None


def encargar_tarea(descripcion, carpeta=""):
    global _pendiente
    descripcion = (descripcion or "").strip()
    if not descripcion:
        return "Dime qué tarea quieres que haga."
    if time.time() - _ultimo_externo < BLOQUEO_EXTERNO:
        return ("Por seguridad no encargo tareas justo después de leer correos, archivos o internet. "
                "Si eres tú quien lo quiere, pídemelo de nuevo en unos minutos.")
    if _actual:
        return f"Ya estoy con otra tarea: «{_actual['descripcion']}». Espera a que termine o cancélala."
    if carpeta:
        destino = pc.ruta_segura(carpeta)
        if not destino.is_dir():
            destino = destino.parent
    else:
        destino = Path(CARPETA_DEFECTO)
        destino.mkdir(parents=True, exist_ok=True)
    _pendiente = {"descripcion": descripcion, "carpeta": destino, "momento": time.time()}
    return (f"Pide al usuario que confirme. Dile exactamente: ¿Quieres que haga esto: «{descripcion}», en la "
            f"carpeta {destino.name}? Di sí o adelante para empezar, o no para cancelar.")


def estado_tarea():
    if not _actual:
        return "No estoy haciendo ninguna tarea ahora."
    minutos = int((time.time() - _actual["inicio"]) // 60)
    return f"Sigo con «{_actual['descripcion']}» desde hace {minutos} minutos."


def cancelar_tarea():
    global _pendiente
    if _pendiente:
        _pendiente = None
        return "Cancelada la tarea que estaba pendiente de confirmar."
    if not _actual:
        return "No hay ninguna tarea en marcha."
    _actual["cancelada"] = True
    if _actual.get("proceso"):
        _matar(_actual["proceso"])
    return f"He parado la tarea «{_actual['descripcion']}»."


HERRAMIENTAS = [
    {
        "name": "encargar_tarea",
        "description": "Encarga a Claude Code una tarea grande en el PC (organizar archivos, programar, crear o "
                       "editar documentos, preparar informes). Usala solo cuando el usuario lo pida con sus "
                       "palabras. Necesita la confirmacion del usuario: repite lo que devuelve.",
        "input_schema": {"type": "object", "properties": {
            "descripcion": {"type": "string", "description": "la tarea completa y concreta, con los detalles"},
            "carpeta": {"type": "string", "description": "opcional: carpeta donde trabajar"}},
            "required": ["descripcion"]},
    },
    {
        "name": "estado_tarea",
        "description": "Dice si hay una tarea encargada en marcha y cuanto lleva.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancelar_tarea",
        "description": "Cancela la tarea encargada (pendiente o en marcha).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def ejecutar(nombre, args):
    """Ejecuta una herramienta de tareas. Devuelve None si el nombre no es de este modulo."""
    try:
        if nombre == "encargar_tarea":
            return encargar_tarea(args.get("descripcion", ""), args.get("carpeta") or "")
        if nombre == "estado_tarea":
            return estado_tarea()
        if nombre == "cancelar_tarea":
            return cancelar_tarea()
    except (PermissionError, FileNotFoundError) as e:
        return f"No se pudo: {e}."
    return None
