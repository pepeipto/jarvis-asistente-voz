"""
WhatsApp: Jarvis te escribe (y mas adelante te escucha) por la API oficial de Meta (WhatsApp Cloud API).

Parte 1: envio de mensajes.
- Dentro de las 24 h siguientes a tu ultimo mensaje se envia texto libre. Fuera de esa ventana Meta
  solo admite una plantilla aprobada (WHATSAPP_PLANTILLA, por defecto "aviso_jarvis") con un parametro
  de texto, asi que el aviso se manda dentro de la plantilla.
- El momento de tu ultimo mensaje se guarda en whatsapp_estado.json para que sobreviva a un reinicio.

Seguridad:
- El token y el numero salen de .env (nunca van al repositorio) y se leen en cada llamada.
- Solo se escribe a WHATSAPP_MI_NUMERO: ningun texto de la IA ni de fuera puede cambiar el destinatario.
- Si WhatsApp falla, solo se anota el tipo de fallo en errores_log.txt (nunca el texto del mensaje).
"""
import json
import os
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

import requests

import registro

API_VERSION_DEFECTO = "v23.0"
PLANTILLA_DEFECTO = "aviso_jarvis"
VENTANA = 24 * 3600             # segundos desde tu ultimo mensaje en los que vale el texto libre
MAX_TEXTO = 4096                # maximo de caracteres de un mensaje de WhatsApp
MAX_PLANTILLA = 1000            # maximo de caracteres del parametro de la plantilla
MAX_ENVIADOS = 50               # mensajes recordados para poder reenviarlos con plantilla

ESTADO = Path(__file__).resolve().with_name("whatsapp_estado.json")
_cache_estado = None            # copia en memoria del json (None = aun sin leer)
_cerrojo = threading.Lock()
_enviados = OrderedDict()       # id de mensaje -> texto enviado


def _post(url, json, headers):
    """POST a la API de Meta; devuelve el JSON de la respuesta o lanza RuntimeError si trae 'error'."""
    r = requests.post(url, json=json, headers=headers, timeout=15)
    try:
        datos = r.json()
    except ValueError:
        datos = {}
    if isinstance(datos, dict) and datos.get("error"):
        raise RuntimeError(str(datos["error"].get("message", "error de Meta")))
    r.raise_for_status()
    return datos


# ---------------------------------------------------------------- configuracion

def _token():
    return os.getenv("WHATSAPP_TOKEN", "").strip()


def _phone_id():
    return os.getenv("WHATSAPP_PHONE_ID", "").strip()


def mi_numero() -> str:
    """Tu numero solo con digitos (sin +, espacios ni guiones)."""
    return re.sub(r"\D", "", os.getenv("WHATSAPP_MI_NUMERO", ""))


def configurado() -> bool:
    return bool(_token() and _phone_id() and mi_numero())


def _plantilla():
    return os.getenv("WHATSAPP_PLANTILLA", "").strip() or PLANTILLA_DEFECTO


def _url():
    version = os.getenv("WHATSAPP_API_VERSION", "").strip() or API_VERSION_DEFECTO
    return f"https://graph.facebook.com/{version}/{_phone_id()}/messages"


# ---------------------------------------------------------------- estado en disco

def _leer_estado() -> dict:
    """Estado {"ultimo_recibido": float, "citas_avisadas": {clave: momento}}; se lee del disco una vez."""
    global _cache_estado
    with _cerrojo:
        if _cache_estado is None:
            try:
                datos = json.loads(ESTADO.read_text(encoding="utf-8"))
                if not isinstance(datos, dict):
                    datos = {}
            except (OSError, ValueError):
                datos = {}
            datos.setdefault("ultimo_recibido", 0.0)
            datos.setdefault("citas_avisadas", {})
            _cache_estado = datos
        return json.loads(json.dumps(_cache_estado))      # copia: quien llama no toca la cache


def _guardar_estado(d: dict):
    global _cache_estado
    with _cerrojo:
        _cache_estado = d
        try:
            ESTADO.write_text(json.dumps(d), encoding="utf-8")
        except OSError as e:
            registro.error("whatsapp", f"no pude guardar el estado ({type(e).__name__})", "sigo en memoria")


def marcar_recibido(momento: float = None):
    """Anota que acabas de escribirle a Jarvis (abre la ventana de 24 h)."""
    d = _leer_estado()
    d["ultimo_recibido"] = time.time() if momento is None else float(momento)
    _guardar_estado(d)


def en_ventana(ahora: float = None) -> bool:
    ahora = time.time() if ahora is None else ahora
    ultimo = _leer_estado()["ultimo_recibido"]
    return bool(ultimo) and 0 <= ahora - ultimo < VENTANA


# ---------------------------------------------------------------- formato del texto

def para_whatsapp(texto: str) -> list:
    """Pasa el Markdown a formato WhatsApp (**negrita** -> *negrita*) y lo parte en trozos de <= 4096."""
    texto = re.sub(r"\*\*(.+?)\*\*", r"*\1*", texto or "", flags=re.S)
    texto = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", texto, flags=re.M)
    texto = texto.strip()
    trozos = []
    while len(texto) > MAX_TEXTO:
        corte = texto.rfind("\n", 0, MAX_TEXTO)
        if corte < MAX_TEXTO // 2:
            corte = texto.rfind(" ", 0, MAX_TEXTO)
        if corte < MAX_TEXTO // 2:
            corte = MAX_TEXTO
        trozos.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto:
        trozos.append(texto)
    return trozos


def texto_plantilla(texto: str) -> str:
    """Los parametros de plantilla no admiten saltos de linea, tabuladores ni 4+ espacios seguidos."""
    return re.sub(r"\s+", " ", texto or "").strip()[:MAX_PLANTILLA]


# ---------------------------------------------------------------- envio

def _cuerpo_texto(trozo):
    return {"messaging_product": "whatsapp", "to": mi_numero(), "type": "text", "text": {"body": trozo}}


def _cuerpo_plantilla(texto):
    return {"messaging_product": "whatsapp", "to": mi_numero(), "type": "template",
            "template": {"name": _plantilla(), "language": {"code": "es"},
                         "components": [{"type": "body",
                                         "parameters": [{"type": "text", "text": texto_plantilla(texto)}]}]}}


def _mandar(cuerpo, texto) -> bool:
    """Envia un cuerpo ya montado. Recuerda el id para poder reenviarlo con plantilla."""
    try:
        resp = _post(_url(), cuerpo, {"Authorization": f"Bearer {_token()}",
                                      "Content-Type": "application/json"})
    except Exception as e:
        registro.error("whatsapp", f"no se pudo enviar ({type(e).__name__})", "sigo sin WhatsApp")
        return False
    try:
        id_msg = resp["messages"][0]["id"]
    except (KeyError, IndexError, TypeError):
        id_msg = None
    if id_msg:
        with _cerrojo:
            _enviados[id_msg] = texto
            while len(_enviados) > MAX_ENVIADOS:
                _enviados.popitem(last=False)
    return True


def enviar(texto: str) -> bool:
    """Te manda un mensaje. Texto libre dentro de la ventana de 24 h; si no, dentro de la plantilla."""
    if not configurado():
        return False
    trozos = para_whatsapp(texto)
    if not trozos:
        return False
    if en_ventana():
        return all([_mandar(_cuerpo_texto(t), t) for t in trozos])
    return _mandar(_cuerpo_plantilla(" ".join(trozos)), texto)


def reenviar_con_plantilla(id_mensaje: str) -> bool:
    """Repite con la plantilla un mensaje que Meta no pudo entregar como texto libre."""
    with _cerrojo:
        texto = _enviados.get(id_mensaje)
    if texto is None or not configurado():
        return False
    return _mandar(_cuerpo_plantilla(texto), texto)
