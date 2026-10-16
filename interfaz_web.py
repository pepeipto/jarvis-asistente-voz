"""
Interfaz 3D de JARVIS.

Arranca un pequeño servidor SOLO local (127.0.0.1) y abre una ventana de tu navegador
(Chrome o Edge en modo aplicacion) con una escena 3D (WebGL / Three.js) en la carpeta ui/.
Jarvis le envia el estado y el nivel de audio en tiempo real; lo que escribas en la caja
de texto vuelve a Jarvis. No hay que instalar nada extra.

Tiene la misma API que la ventana clasica (interfaz.py):
  set_estado, set_nivel, simular, log, cerrar, cola_texto, run
"""
import json
import math
import mimetypes
import os
import queue
import secrets
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

UI_DIR = Path(__file__).resolve().parent / "ui"
PUERTO_BASE = 8765
ESTADOS = {"inactivo", "escuchando", "pensando", "hablando", "error"}

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/ttf", ".ttf")


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass                      # conexiones cortadas por el navegador: no ensuciar la consola


class OrbeWeb:
    def __init__(self, info=None, puerto=PUERTO_BASE):
        self.info = info or (lambda: {})
        self.token = secrets.token_urlsafe(16)
        self.estado_actual = "inactivo"
        self._obj = 0.0              # nivel objetivo (0..1), lo escriben los hilos de audio
        self._nivel = 0.0            # nivel suavizado que se envia a la ventana
        self._sim_hasta = 0.0
        self.mensajes = []           # [[rol, texto], ...]
        self._ver = 0                # sube cada vez que cambian los mensajes
        self.cola_texto = queue.Queue()
        self._fin = threading.Event()
        self._clientes = 0
        self._hubo_cliente = False
        self._sin_clientes_desde = None
        self.t0 = time.time()
        self.proc = None
        self.fps = None              # fotogramas por segundo que informa la ventana 3D

        orbe = self

        class Manejador(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):          # silencio en la consola
                pass

            # ---------------------------------------------------------- seguridad
            def _host_ok(self):
                host = (self.headers.get("Host") or "").lower()
                return host in (f"127.0.0.1:{orbe.puerto}", f"localhost:{orbe.puerto}")

            def _token_ok(self):
                t = parse_qs(urlparse(self.path).query).get("t", [""])[0]
                return secrets.compare_digest(t, orbe.token)

            def _origen_ok(self):
                o = self.headers.get("Origin")
                return o is None or o in (f"http://127.0.0.1:{orbe.puerto}", f"http://localhost:{orbe.puerto}")

            def _responder(self, codigo, cuerpo=b"", tipo="text/plain; charset=utf-8"):
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if cuerpo:
                    self.wfile.write(cuerpo)

            # ---------------------------------------------------------- rutas
            def do_GET(self):
                if not self._host_ok():
                    return self._responder(403)
                ruta = urlparse(self.path).path
                if ruta == "/eventos":
                    return self._eventos() if self._token_ok() else self._responder(403)
                if ruta == "/datos":
                    if not self._token_ok():
                        return self._responder(403)
                    try:
                        d = dict(orbe.info())
                    except Exception as e:
                        d = {"error": str(e)}
                    d["activo_seg"] = int(time.time() - orbe.t0)
                    return self._responder(200, json.dumps(d).encode(), "application/json; charset=utf-8")
                return self._estatico(ruta)

            def do_POST(self):
                if not (self._host_ok() and self._origen_ok() and self._token_ok()):
                    return self._responder(403)
                ruta = urlparse(self.path).path
                if ruta == "/telemetria":
                    try:
                        n = min(int(self.headers.get("Content-Length", "0")), 500)
                        orbe.fps = float(json.loads(self.rfile.read(n) or b"{}").get("fps"))
                    except Exception:
                        pass
                    return self._responder(204)
                if ruta != "/enviar":
                    return self._responder(404)
                try:
                    n = min(int(self.headers.get("Content-Length", "0")), 8000)
                    texto = str(json.loads(self.rfile.read(n) or b"{}").get("texto", "")).strip()[:2000]
                except Exception:
                    return self._responder(400)
                if texto:
                    orbe.cola_texto.put(texto)
                self._responder(204)

            def _estatico(self, ruta):
                rel = "index.html" if ruta in ("/", "") else ruta.lstrip("/")
                f = (UI_DIR / rel).resolve()
                if UI_DIR.resolve() not in f.parents or not f.is_file():
                    return self._responder(404)
                tipo = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if tipo.startswith("text/") or tipo == "application/javascript":
                    tipo += "; charset=utf-8"
                self._responder(200, f.read_bytes(), tipo)

            def _eventos(self):
                """Flujo continuo (Server-Sent Events) con el estado y el nivel de audio."""
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                orbe._clientes += 1
                orbe._hubo_cliente = True
                orbe._sin_clientes_desde = None
                ver = -1
                try:
                    while not orbe._fin.is_set():
                        d = {"e": orbe.estado_actual, "n": round(orbe._nivel, 3)}
                        if orbe._ver != ver:
                            ver = orbe._ver
                            d["m"] = list(orbe.mensajes)
                        self.wfile.write(b"data: " + json.dumps(d, ensure_ascii=False).encode() + b"\n\n")
                        self.wfile.flush()
                        time.sleep(0.033)
                except OSError:
                    pass
                finally:
                    orbe._clientes -= 1
                    if orbe._clientes <= 0:
                        orbe._sin_clientes_desde = time.time()
                    self.close_connection = True

        self._srv = None
        for p in range(puerto, puerto + 25):
            try:
                self.puerto = p
                self._srv = _Servidor(("127.0.0.1", p), Manejador)
                break
            except OSError:
                continue
        if self._srv is None:
            raise OSError("no hay ningun puerto libre para la interfaz")
        self._srv.daemon_threads = True

    # ------------------------------------------------------------ API para otros hilos
    def set_estado(self, nombre):
        self.estado_actual = nombre if nombre in ESTADOS else "inactivo"

    def set_nivel(self, x):
        self._obj = max(self._obj * 0.6, max(0.0, min(1.0, float(x))))

    def simular(self, segundos):
        self._sim_hasta = time.time() + segundos

    def log(self, rol, texto):
        self.mensajes.append([rol, texto])
        del self.mensajes[:-8]
        self._ver += 1

    def editar_ultimo(self, rol, texto):
        """Cambia el texto del ultimo mensaje de ese rol (para mostrar la respuesta mientras se genera)."""
        for m in reversed(self.mensajes):
            if m[0] == rol:
                m[1] = texto
                self._ver += 1
                return

    def cerrar(self):
        self._fin.set()

    # ------------------------------------------------------------ ciclo de vida
    def _latido(self):
        """Suaviza el nivel de audio ~60 veces por segundo."""
        while not self._fin.is_set():
            ahora = time.time()
            obj = self._obj
            if ahora < self._sim_hasta:
                t = ahora - self.t0
                obj = max(obj, 0.30 + 0.30 * abs(math.sin(t * 7.3)) * (0.6 + 0.4 * math.sin(t * 2.1)))
            self._nivel += (obj - self._nivel) * (0.55 if obj > self._nivel else 0.12)
            self._obj *= 0.90
            time.sleep(0.016)

    def _abrir_ventana(self, url):
        if os.environ.get("JARVIS_NO_BROWSER"):
            return
        candidatos = []
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                b = Path(base)
                candidatos += [b / "Google/Chrome/Application/chrome.exe",
                               b / "Microsoft/Edge/Application/msedge.exe",
                               b / "BraveSoftware/Brave-Browser/Application/brave.exe"]
        exe = next((c for c in candidatos if c.exists()), None)
        if exe:
            perfil = Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".") / "jarvis-ui-perfil"
            try:
                self.proc = subprocess.Popen([
                    str(exe), f"--app={url}", f"--user-data-dir={perfil}", "--window-size=1500,940",
                    "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
                    "--autoplay-policy=no-user-gesture-required"])
                return
            except OSError:
                pass
        webbrowser.open(url)

    def run(self):
        """Arranca el servidor, abre la ventana y espera hasta que se cierre."""
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        threading.Thread(target=self._latido, daemon=True).start()
        url = f"http://127.0.0.1:{self.puerto}/?t={self.token}"
        self._abrir_ventana(url)
        print(f"[Jarvis] Interfaz 3D en http://127.0.0.1:{self.puerto}/  (cierra la ventana para apagar a Jarvis)")
        try:
            while not self._fin.is_set():
                time.sleep(0.25)
                # ventana cerrada: sin clientes durante 8 s despues de haber tenido alguno
                if self._hubo_cliente and self._clientes <= 0 and self._sin_clientes_desde \
                        and time.time() - self._sin_clientes_desde > 8:
                    break
        finally:
            self._fin.set()
            if self.proc:
                try:
                    self.proc.terminate()
                except OSError:
                    pass
