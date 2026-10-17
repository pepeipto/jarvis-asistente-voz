"""
WhatsApp: Jarvis te escribe (y mas adelante te escucha) por la API oficial de Meta (WhatsApp Cloud API).

Parte 1: envio de mensajes.
- Dentro de las 24 h siguientes a tu ultimo mensaje se envia texto libre. Fuera de esa ventana Meta
  solo admite una plantilla aprobada (WHATSAPP_PLANTILLA, por defecto "aviso_jarvis") con un parametro
  de texto, asi que el aviso se manda dentro de la plantilla.
- El momento de tu ultimo mensaje se guarda en whatsapp_estado.json para que sobreviva a un reinicio.

Parte 2: receptor del webhook (HTTP solo en 127.0.0.1; ngrok lo expone a internet).
- Toda peticion POST debe traer la firma X-Hub-Signature-256 (HMAC-SHA256 del cuerpo con el secreto de la app).
- Solo se atienden los mensajes de WHATSAPP_MI_NUMERO; los de cualquier otro numero se descartan sin rastro.
- Cada mensaje se atiende una vez (id) y como mucho 20 por minuto.

Seguridad:
- El token y el numero salen de .env (nunca van al repositorio) y se leen en cada llamada.
- Solo se escribe a WHATSAPP_MI_NUMERO: ningun texto de la IA ni de fuera puede cambiar el destinatario.
- Si WhatsApp falla, solo se anota el tipo de fallo en errores_log.txt (nunca el texto del mensaje).
"""
import hashlib
import hmac
import json
import os
import queue
import re
import threading
import time
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

import registro

API_VERSION_DEFECTO = "v23.0"
PLANTILLA_DEFECTO = "aviso_jarvis"
VENTANA = 24 * 3600             # segundos desde tu ultimo mensaje en los que vale el texto libre
MAX_TEXTO = 4096                # maximo de caracteres de un mensaje de WhatsApp
MAX_PLANTILLA = 1000            # maximo de caracteres del parametro de la plantilla
MAX_ENVIADOS = 50               # mensajes recordados para poder reenviarlos con plantilla
PUERTO_DEFECTO = 8766
MAX_POR_MINUTO = 20             # mensajes tuyos que se atienden por minuto
MAX_VISTOS = 500                # ids de mensajes recordados para no atender dos veces el mismo
MAX_CUERPO = 1_000_000          # bytes maximos de una peticion
ERROR_FUERA_DE_VENTANA = 131047 # Meta: no se puede mandar texto libre fuera de las 24 h
AVISO_NO_TEXTO = "Por ahora solo leo texto."

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


def _app_secret():
    return os.getenv("WHATSAPP_APP_SECRET", "").strip()


def _verify_token():
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()


def _puerto():
    try:
        return int(os.getenv("WHATSAPP_PUERTO", "").strip() or PUERTO_DEFECTO)
    except ValueError:
        return PUERTO_DEFECTO


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


# ---------------------------------------------------------------- receptor

al_recibir = None               # funcion(texto) que asigna jarvis.py; recibe cada mensaje tuyo aceptado
_cola = queue.Queue()           # tareas pendientes: ("texto", str) | ("aviso", str) | ("plantilla", id)
_vistos = OrderedDict()         # ids de mensajes ya atendidos
_momentos = deque()             # cuando se aceptaron los ultimos mensajes (limite por minuto)
_servidor = None
_hilo_servidor = None
_hilo_despacho = None
_parar = threading.Event()


def _reiniciar_receptor():
    """Vacia la memoria del receptor (cola, ids vistos y contador por minuto)."""
    with _cerrojo:
        _vistos.clear()
        _momentos.clear()
    while True:
        try:
            _cola.get_nowait()
        except queue.Empty:
            break


def _cabecera(cabeceras, nombre):
    nombre = nombre.lower()
    for k, v in (cabeceras or {}).items():
        if str(k).lower() == nombre:
            return v
    return None


def firma_valida(cuerpo: bytes, cabecera: str) -> bool:
    """True solo si la cabecera es el HMAC-SHA256 del cuerpo con el secreto de la app (comparacion en tiempo constante)."""
    secreto = _app_secret()
    if not secreto or not isinstance(cabecera, str) or not isinstance(cuerpo, (bytes, bytearray)):
        return False
    esperada = "sha256=" + hmac.new(secreto.encode("utf-8"), bytes(cuerpo), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada.encode("utf-8"), cabecera.strip().encode("utf-8"))


def _verificar(consulta):
    """Alta del webhook en Meta: devuelve el 'challenge' si el token coincide."""
    q = parse_qs(consulta)
    token = (q.get("hub.verify_token") or [""])[0]
    reto = (q.get("hub.challenge") or [""])[0]
    esperado = _verify_token()
    if (esperado and (q.get("hub.mode") or [""])[0] == "subscribe"
            and hmac.compare_digest(token.encode("utf-8"), esperado.encode("utf-8"))):
        return 200, reto.encode("utf-8")
    return 403, b"prohibido"


def _lista(x):
    return x if isinstance(x, list) else []


def _dict(x):
    return x if isinstance(x, dict) else {}


def _admitir(id_msg) -> bool:
    """False si el mensaje ya se atendio o se pasa del limite por minuto; si no, lo anota."""
    ahora = time.time()
    with _cerrojo:
        if id_msg in _vistos:
            return False
        while _momentos and ahora - _momentos[0] >= 60:
            _momentos.popleft()
        if len(_momentos) >= MAX_POR_MINUTO:
            return False
        _momentos.append(ahora)
        _vistos[id_msg] = True
        while len(_vistos) > MAX_VISTOS:
            _vistos.popitem(last=False)
    return True


def _atender_mensaje(m, mio):
    if not mio or re.sub(r"\D", "", str(m.get("from", ""))) != mio:
        return                                          # de otro numero: se descarta sin rastro
    id_msg = m.get("id")
    if not isinstance(id_msg, str) or not id_msg or not _admitir(id_msg):
        return
    marcar_recibido()
    if m.get("type") == "text":
        cuerpo = _dict(m.get("text")).get("body")
        if isinstance(cuerpo, str) and cuerpo.strip():
            _cola.put(("texto", cuerpo.strip()[:MAX_TEXTO]))
    else:
        _cola.put(("aviso", AVISO_NO_TEXTO))


def _atender_estado(st):
    if st.get("status") != "failed":
        return
    for e in _lista(st.get("errors")):
        codigo = _dict(e).get("code")
        if codigo == ERROR_FUERA_DE_VENTANA and isinstance(st.get("id"), str):
            _cola.put(("plantilla", st["id"]))
        elif isinstance(codigo, int):
            registro.error("whatsapp", f"Meta no pudo entregar un mensaje (codigo {codigo})", "sigo")


def procesar_peticion(metodo: str, ruta: str, cabeceras: dict, cuerpo: bytes):
    """Logica pura del webhook: devuelve (codigo HTTP, cuerpo). Lo que hay que hacer queda en la cola."""
    partes = urlsplit(ruta)
    if partes.path != "/whatsapp":
        return 404, b"no encontrado"
    if metodo == "GET":
        return _verificar(partes.query)
    if metodo != "POST":
        return 405, b"metodo no permitido"
    if not firma_valida(cuerpo, _cabecera(cabeceras, "X-Hub-Signature-256")):
        registro.error("whatsapp", "peticion rechazada: firma no valida", "la ignoro")
        return 403, b"firma no valida"
    try:
        datos = json.loads(cuerpo.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 200, b"ok"                               # firmado pero ilegible: 200 para que Meta no reintente
    mio = mi_numero()
    for entrada in _lista(_dict(datos).get("entry")):
        for cambio in _lista(_dict(entrada).get("changes")):
            valor = _dict(_dict(cambio).get("value"))
            for m in _lista(valor.get("messages")):
                _atender_mensaje(_dict(m), mio)
            for st in _lista(valor.get("statuses")):
                _atender_estado(_dict(st))
    return 200, b"ok"


def _entregar(tarea):
    tipo, dato = tarea
    try:
        if tipo == "texto":
            if al_recibir is not None:
                al_recibir(dato)
        elif tipo == "aviso":
            enviar(dato)
        elif tipo == "plantilla":
            reenviar_con_plantilla(dato)
    except Exception as e:
        registro.error("whatsapp", f"fallo al atender un mensaje ({type(e).__name__})", "sigo")


def _despachar():
    """Entrega todo lo pendiente de la cola (en el receptor lo hace un hilo aparte)."""
    while True:
        try:
            tarea = _cola.get_nowait()
        except queue.Empty:
            return
        _entregar(tarea)


def _bucle_despacho():
    while not _parar.is_set():
        try:
            tarea = _cola.get(timeout=0.5)
        except queue.Empty:
            continue
        _entregar(tarea)


class _Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):                       # nada en la consola
        pass

    def _responder(self, codigo, cuerpo):
        self.send_response(codigo)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _atender(self, metodo):
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            largo = -1
        if largo < 0 or largo > MAX_CUERPO:
            self._responder(413, b"demasiado grande")
            return
        cuerpo = self.rfile.read(largo) if largo else b""
        try:
            codigo, resp = procesar_peticion(metodo, self.path, dict(self.headers.items()), cuerpo)
        except Exception as e:
            registro.error("whatsapp", f"fallo en el webhook ({type(e).__name__})", "respondo 500")
            codigo, resp = 500, b"error"
        self._responder(codigo, resp)

    def do_GET(self):
        self._atender("GET")

    def do_POST(self):
        self._atender("POST")


class _Servidor(ThreadingHTTPServer):
    allow_reuse_address = False                         # en Windows permitiria compartir un puerto ocupado
    daemon_threads = True


def iniciar_receptor() -> bool:
    """Arranca el webhook en 127.0.0.1. False (sin lanzar nada) si falta configuracion o secreto, o el puerto esta ocupado."""
    global _servidor, _hilo_servidor, _hilo_despacho
    if _servidor is not None:
        return True
    if not configurado() or not _app_secret():
        return False
    try:
        servidor = _Servidor(("127.0.0.1", _puerto()), _Manejador)
    except (OSError, OverflowError) as e:
        registro.error("whatsapp", f"no pude abrir el puerto del webhook ({type(e).__name__})", "sin WhatsApp entrante")
        return False
    _parar.clear()
    _servidor = servidor
    _hilo_servidor = threading.Thread(target=servidor.serve_forever, name="whatsapp-web", daemon=True)
    _hilo_despacho = threading.Thread(target=_bucle_despacho, name="whatsapp-despacho", daemon=True)
    _hilo_servidor.start()
    _hilo_despacho.start()
    return True


def parar_receptor() -> None:
    global _servidor, _hilo_servidor, _hilo_despacho
    servidor, _servidor = _servidor, None
    _parar.set()
    if servidor is not None:
        servidor.shutdown()
        servidor.server_close()
    for h in (_hilo_servidor, _hilo_despacho):
        if h is not None and h.is_alive():
            h.join(timeout=2)
    _hilo_servidor = _hilo_despacho = None
