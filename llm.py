"""
Cerebro de IA de Jarvis: Ollama (local y gratis) y Anthropic (Claude).

El historial de conversacion usa un formato neutro, asi se puede cambiar de proveedor
a mitad de conversacion (por ejemplo, si Anthropic se queda sin saldo, Ollama sigue):
  {"role": "user", "content": "texto"}
  {"role": "assistant", "content": "texto", "tool_calls": [{"id", "name", "args"}]}
  {"role": "tool", "id": "...", "name": "...", "content": "resultado"}
"""
import json
import os
import re
import time

import requests

OLLAMA_URL = (os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
MODELO_SUGERIDO = "granite4.1:8b"   # el instalador elige qwen3.8:27b si la grafica tiene 20 GB o mas

# Familias de modelos que soportan herramientas, de mejor a peor para este uso (español + herramientas)
PREFERIDOS = ["qwen3.8", "qwen3", "qwen2.5", "llama3.3", "llama3.1", "mistral-nemo", "gpt-oss", "llama3.2",
              "mistral", "phi4-mini", "granite"]
MAX_VUELTAS = 6          # maximo de rondas de herramientas por peticion

# Peticiones que suelen requerir herramienta, y respuestas que afirman haber hecho algo.
# Los modelos locales a veces dicen "lo he apuntado" sin llamar a la herramienta: se detecta y se corrige.
INTENCION = re.compile(r"\b(apunt\w*|anot\w*|guard\w*|recu[eé]rd\w*|añad\w*|agend\w*|memoriz\w*|diario|notas?)\b", re.I)
AFIRMA = re.compile(r"\b(he (guardado|apuntado|anotado|añadido|registrado|creado|buscado|encontrado)|"
                    r"(queda|qued[oó]|est[aá]) (guardad|apuntad|anotad|registrad)\w*)", re.I)
AVISO_SIN_HERRAMIENTA = ("[Aviso del sistema] En esta respuesta no has llamado a ninguna herramienta, asi que no se ha "
                         "guardado ni buscado nada. Si el usuario pidio guardar, apuntar o consultar algo de su cerebro, "
                         "llama ahora a la herramienta adecuada. Si no hacia falta ninguna, responde de nuevo sin afirmar "
                         "que has guardado o encontrado algo.")
CTX = int(os.getenv("OLLAMA_CTX") or 0)
# Buscador de Claude (servidor de Anthropic): busca en todo internet y cita fuentes. La version 20260209 no
# funciona a traves de OmniRoute (medido el 17/10/2026); la 20250305 si. BUSQUEDA_CLAUDE=0 lo desactiva.
BUSQUEDA_CLAUDE = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5,
                   "user_location": {"type": "approximate", "country": "ES", "timezone": "Europe/Madrid"}}
APARTAR = 600               # s sin reintentar un proveedor sin saldo o con la clave mal (no se arregla solo)
ESPERA_PRIMER_TOKEN = 4.0    # segundos sin respuesta de la nube antes de pasar al modelo gratuito
INACTIVIDAD = 240            # tras 4 min sin usar la nube, la primera respuesta tarda ~3 s mas: aviso minimo    # 0 = automatico (8192, o 6144 en modelos de 30B o mas)


RESPUESTA_RAPIDA = (os.getenv("RESPUESTA_RAPIDA") or "1") != "0"
CONSULTAS = {"buscar_en_cerebro", "leer_nota", "notas_recientes", "procesar_bandeja", "leer_web", "tiempo",
             "calendario_eventos", "correo_buscar", "correo_leer", "drive_buscar", "drive_leer",
             "buscar_archivos", "leer_archivo", "listar_carpeta", "buscar_web"}
ESPERAS = ["Déjame mirar. ", "Un momento. ", "Lo compruebo. "]


def confirmacion_directa(calls, resultados):
    """Si solo se usaron herramientas de 'hacer' (guardar, abrir...) y todo fue bien, devuelve una
    confirmacion corta sin pedirle otra vuelta a la IA (ahorra ~1 s). Si no, None."""
    frases = []
    for c, res in zip(calls, resultados):
        if res.lower().startswith(("error", "no conozco", "no encuentro", "ruta no valida", "no se pudo")):
            return None
        n = c["name"]
        if n == "anadir_al_diario":
            frases.append("Anotado en tu diario.")
        elif n == "guardar_nota":
            t = (c["args"].get("titulo") or "").strip()
            frases.append(f"Guardado en tus notas: {t}." if t else "Guardado en tus notas.")
        elif n in ("abrir_aplicacion", "abrir_programa", "abrir_carpeta"):
            frases.append(res)
        elif n == "abrir_web":
            frases.append(res if res.startswith("Por seguridad") else "Abierto en el navegador.")
        elif n in ("calendario_crear", "correo_enviar", "drive_crear_documento"):
            frases.append(res)
        elif n == "correo_borrador":
            frases.append("Te he dejado el borrador en Gmail para que lo revises y lo envíes tú.")
        else:
            return None                          # consultas (buscar, leer, hora...): la IA debe responder
    unicas = list(dict.fromkeys(frases))
    return " ".join(unicas) if unicas else None


class IAError(Exception):
    """Error de IA con un texto corto para decir en voz alta y otro con el detalle para la pantalla."""

    def __init__(self, hablado, detalle, permanente=False):
        super().__init__(detalle)
        self.hablado = hablado
        self.detalle = detalle
        self.permanente = permanente        # sin saldo o clave mala: reintentar enseguida no sirve


def _limpiar(texto):
    """Quita bloques <think>...</think> que algunos modelos locales incluyen."""
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()


MARCA_BUSQUEDA = "[registro interno de Jarvis, no se dice en voz alta]"
_MARCA_RE = re.compile(r"\s*\[registro interno de Jarvis[^\]]*\][^\n]*", re.I)


def _fuentes(bloques):
    """Lo que busco Claude en internet y las paginas que obtuvo, en una linea (o "" si no busco)."""
    consultas, paginas = [], []
    for b in bloques:
        if getattr(b, "type", "") == "server_tool_use":
            q = (getattr(b, "input", None) or {}).get("query")
            if q:
                consultas.append(f"«{q}»")
        elif getattr(b, "type", "") == "web_search_tool_result":
            for r in (getattr(b, "content", None) or [])[:5] if isinstance(getattr(b, "content", None), list) else []:
                if getattr(r, "url", None):
                    paginas.append(f"{getattr(r, 'title', '') or ''} ({r.url})".strip())
    if not consultas:
        return ""
    return (f"{MARCA_BUSQUEDA} Para esta respuesta busqué en internet con web_search: {', '.join(consultas)}."
            + (f" Resultados: {'; '.join(paginas[:8])}." if paginas else ""))


def _a_dict(x):
    """Bloque de la respuesta (objeto del SDK) a dict para guardarlo y reenviarlo tal cual."""
    if hasattr(x, "model_dump"):
        return x.model_dump(exclude_none=True)
    if isinstance(x, list):
        return [_a_dict(v) for v in x]
    if hasattr(x, "__dict__"):
        return {k: _a_dict(v) for k, v in vars(x).items() if v is not None}
    return x


def _con_fuentes(m):
    """Texto del asistente para reenviarlo a la IA, con lo que busco (para que sepa que no se lo invento)."""
    return f"{m.get('content', '')}\n\n{m['busquedas']}".strip() if m.get("busquedas") else m.get("content", "")


def _limpiar_parcial(texto):
    """Version de _limpiar para texto que aun se esta generando."""
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    i = t.find("<think>")
    t = t[:i] if i != -1 else t
    j = t.find("[registro interno")                 # si la IA imitara la marca, no se dice en voz alta
    return (t[:j] if j != -1 else t).lstrip()


def _tamano(nombre):
    """'qwen2.5:32b' -> 32.0 ; sin tamano -> 0"""
    m = re.search(r"(\d+(?:\.\d+)?)b", nombre.lower().split(":")[-1])
    return float(m.group(1)) if m else 0.0


def _ctx(modelo):
    return CTX or (6144 if _tamano(modelo) >= 30 else 8192)


def _args(a):
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except ValueError:
            a = {}
    return a if isinstance(a, dict) else {}


class IA:
    def __init__(self, tools, system_fn, run_tool, anthropic_key="", anthropic_model="claude-sonnet-5-5",
                 proveedor="auto", ollama_model="", contexto_fn=None,
                 anthropic_base_url="", anthropic_token="", modelo_respaldo_nube="auto/best-free"):
        self.tools = tools                    # herramientas en formato Anthropic (input_schema)
        self.system_fn = system_fn
        self.run_tool = run_tool
        self.anthropic_key = anthropic_key
        self.anthropic_base_url = anthropic_base_url   # p. ej. OmniRoute (http://localhost:20128)
        self.anthropic_token = anthropic_token         # token Bearer del proxy
        # La API oficial (api.anthropic.com) no es un proxy: va con la clave y sin los nombres "cc/..." de OmniRoute
        self.es_proxy = bool(anthropic_base_url) and "api.anthropic.com" not in anthropic_base_url.lower()
        self.anthropic_model = anthropic_model if self.es_proxy else anthropic_model.split("/")[-1]
        self.modelo_respaldo_nube = modelo_respaldo_nube   # gratuito de OmniRoute si el principal falla
        self.proveedor = (proveedor or "auto").lower()
        self.ollama_model_pref = ollama_model
        self._cliente_anthropic = None
        self._tags_cache = (0.0, None)         # (momento, lista de modelos o None si no responde)
        self._sin_tools = set()                # modelos de Ollama que no aceptan herramientas
        self.activo = ""                       # proveedor que respondio la ultima vez
        self.ultimo_modelo = ""
        self.stats = {}                        # metricas de la ultima respuesta de Ollama
        self.contexto_fn = contexto_fn         # texto (fecha/hora) que se añade al ultimo mensaje del usuario
        self.corregidas = 0                    # veces que el modelo afirmo algo sin usar herramientas
        self._ultimo_arranque = 0.0            # ultima vez que se intento abrir Ollama
        self._proxy_estado = (0.0, True)       # (momento, responde) de la ultima comprobacion de OmniRoute
        self.on_reparacion = None              # funcion(origen, texto) para anotar autorreparaciones
        self._ultimo_uso = 0.0                 # ultima vez que se hablo con la nube
        self._apartado = {}                    # proveedor -> momento hasta el que no se prueba
        self.busqueda_nube = (os.getenv("BUSQUEDA_CLAUDE") or "1") != "0"   # buscador de Claude en todo internet
        self.on_externo = None                 # funcion() cuando la IA lee internet por su cuenta

    # ------------------------------------------------------------------ descubrimiento
    def modelos_ollama(self, forzar=False):
        """Lista de modelos instalados en Ollama, o None si Ollama no responde."""
        t, cache = self._tags_cache
        if not forzar and time.time() - t < 15:
            return cache
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            r.raise_for_status()
            nombres = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            nombres = None
        self._tags_cache = (time.time(), nombres)
        return nombres

    def elegir_modelo_ollama(self, nombres):
        if self.ollama_model_pref:
            for n in nombres:
                if n == self.ollama_model_pref or n.split(":")[0] == self.ollama_model_pref:
                    return n
            return self.ollama_model_pref          # que Ollama diga si no existe
        utiles = [n for n in nombres if "embed" not in n.lower()]

        for fam in PREFERIDOS:
            familia = [n for n in utiles if n.lower().startswith(fam)]
            if familia:
                return max(familia, key=_tamano)     # dentro de la familia, el mas grande (mas listo)
        return utiles[0] if utiles else None

    def describir(self):
        """Texto corto para mostrar en pantalla: que IA se usara."""
        if self._hay_anthropic() and self.proveedor in ("auto", "anthropic"):
            via = " (OmniRoute)" if self.es_proxy else ""
            return f"Claude · {self.anthropic_model}{via}"
        if self.proveedor in ("auto", "ollama"):
            nombres = self.modelos_ollama()
            if nombres:
                m = self.elegir_modelo_ollama(nombres)
                if m:
                    return f"Ollama · {m}"
            if self.proveedor == "ollama":
                return "Ollama (sin conexión)" if nombres is None else "Ollama (sin modelos)"
        return "Sin IA configurada"

    # ------------------------------------------------------------------ punto de entrada
    def responder(self, history, on_texto=None):
        """Genera la respuesta (ejecutando herramientas si hace falta). Modifica history.
        on_texto(trozo) recibe el texto a medida que se genera (para empezar a hablar antes)."""
        orden = self._orden()
        errores = []
        for prov in orden:
            n_antes = len(history)
            try:
                if prov == "ollama":
                    texto = self._ollama(history, on_texto)
                elif prov == "anthropic_gratis":
                    texto = self._anthropic(history, on_texto, modelo=self.modelo_respaldo_nube)
                else:
                    texto = self._anthropic(history, on_texto)
                if not (texto or "").strip():      # nunca quedarse callado: probar el siguiente
                    raise IAError("No me ha llegado respuesta.", f"{prov} devolvio una respuesta vacia")
                self.activo = prov
                return texto
            except IAError as e:
                errores.append(e)
                del history[n_antes:]              # deshacer lo que haya dejado a medias
                if e.permanente:
                    self._apartado[prov] = time.time() + APARTAR
                if self.on_reparacion and prov != orden[-1]:
                    siguiente = orden[orden.index(prov) + 1]
                    self.on_reparacion("ia", f"{prov} fallo ({e.detalle[:120]}): pruebo con {siguiente}")
        # todos fallaron: priorizar el error mas util
        principal = errores[0] if errores else IAError(
            "No tengo ninguna inteligencia configurada.",
            "Configura Ollama (ollama.com) o una clave de Anthropic en el archivo .env")
        if len(errores) > 1:
            principal = IAError(principal.hablado, " | ".join(e.detalle for e in errores))
        raise principal

    def _orden(self):
        """Proveedores a probar, en orden: la nube primero y Ollama solo de respaldo."""
        if self.proveedor == "ollama" or not self._hay_anthropic():
            return ["ollama"]
        if self.proveedor == "auto" and self.es_proxy and not self._proxy_responde():
            return ["ollama"]           # OmniRoute apagado: no esperar ~25 s de reintentos en cada pregunta
        nube = ["anthropic"] + (["anthropic_gratis"] if self.es_proxy and self.modelo_respaldo_nube else [])
        ahora = time.time()
        nube = [p for p in nube if self._apartado.get(p, 0) <= ahora] or (nube if self.proveedor == "anthropic" else [])
        return nube if self.proveedor == "anthropic" else nube + ["ollama"]

    # ------------------------------------------------------------------ Ollama
    def _con_contexto(self, msgs):
        """Añade fecha/hora al ultimo mensaje de texto del usuario (sin tocar el historial guardado)."""
        if not self.contexto_fn:
            return msgs
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i]["role"] == "user" and isinstance(msgs[i]["content"], str):
                msgs[i] = {**msgs[i], "content": f"{msgs[i]['content']}\n\n{self.contexto_fn()}"}
                break
        return msgs

    def arrancar_ollama(self, espera=20):
        """Autorreparacion: si Ollama esta cerrado y es local, lo abre y espera a que responda.
        Como mucho un intento por minuto. Devuelve True si Ollama responde despues."""
        if time.time() - self._ultimo_arranque < 60 or "127.0.0.1" not in OLLAMA_URL and "localhost" not in OLLAMA_URL:
            return False
        self._ultimo_arranque = time.time()
        import shutil
        import subprocess
        exe = shutil.which("ollama") or os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        if not os.path.exists(exe):
            return False
        try:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            return False
        fin = time.time() + espera
        while time.time() < fin:
            if self.modelos_ollama(forzar=True) is not None:
                return True
            time.sleep(1)
        return False

    def _ollama(self, history, on_texto=None):
        nombres = self.modelos_ollama(forzar=True)
        if nombres is None and self.arrancar_ollama():
            if self.on_reparacion:
                self.on_reparacion("ollama", "Ollama estaba cerrado: lo he abierto yo")
            nombres = self.modelos_ollama(forzar=True)
        if nombres is None:
            raise IAError(
                "No consigo conectar con Ollama. Comprueba que está instalado y abierto.",
                f"Ollama no responde en {OLLAMA_URL}. Instálalo desde ollama.com, ábrelo y descarga un modelo "
                f"con: ollama pull {MODELO_SUGERIDO}")
        modelo = self.elegir_modelo_ollama(nombres)
        if not modelo:
            raise IAError(
                "Ollama no tiene ningún modelo descargado.",
                f"Ollama funciona pero no tiene modelos. Abre una ventana de comandos y escribe: "
                f"ollama pull {MODELO_SUGERIDO}")
        self.ultimo_modelo = modelo
        otools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                    "parameters": t["input_schema"]}} for t in self.tools]
        ultima = next((m["content"] for m in reversed(history)
                       if m["role"] == "user" and isinstance(m["content"], str)), "")
        intencion = bool(INTENCION.search(ultima))
        uso, insistido, extra = False, False, []
        dicho = [False]                          # si ya se ha dicho algo en voz alta en esta respuesta

        def decir(t):
            dicho[0] = True
            on_texto(t)
        for _ in range(MAX_VUELTAS):
            msgs = [{"role": "system", "content": self.system_fn()}] + self._con_contexto(self._a_ollama(history)) + extra
            retener = intencion and not uso      # no decir nada en voz alta hasta saber si usa la herramienta
            cuerpo = {"model": modelo, "messages": msgs, "stream": True, "think": False,
                      "keep_alive": "30m", "options": {"temperature": 0.4, "num_ctx": _ctx(modelo)}}
            if modelo not in self._sin_tools:
                cuerpo["tools"] = otools
            try:
                r = requests.post(f"{OLLAMA_URL}/api/chat", json=cuerpo, timeout=300, stream=True)
            except requests.RequestException as e:
                raise IAError("Se ha cortado la conexión con Ollama.", f"Error de conexión con Ollama: {e}")
            if r.status_code == 400 and "tools" in r.text.lower() and "tools" in cuerpo:
                self._sin_tools.add(modelo)        # ese modelo no sabe usar herramientas: reintentar sin ellas
                continue
            if r.status_code == 404:
                raise IAError("Ese modelo no está descargado en Ollama.",
                              f"El modelo '{modelo}' no existe. Descárgalo con: ollama pull {modelo}")
            if r.status_code != 200:
                raise IAError("Ollama ha dado un error.", f"Ollama HTTP {r.status_code}: {r.text[:200]}")
            contenido, emitido, llamadas = "", "", []
            try:
                for linea in r.iter_lines():
                    if not linea:
                        continue
                    d = json.loads(linea)
                    if d.get("error"):
                        raise IAError("Ollama ha dado un error.", f"Ollama: {d['error']}")
                    msg = d.get("message") or {}
                    if msg.get("tool_calls"):
                        llamadas.extend(msg["tool_calls"])
                    if msg.get("content"):
                        contenido += msg["content"]
                        if on_texto and not retener:
                            limpio = _limpiar_parcial(contenido)
                            if len(limpio) > len(emitido) and limpio.startswith(emitido):
                                decir(limpio[len(emitido):])
                                emitido = limpio
                    if d.get("done"):
                        self.stats = d
                        break
            except requests.RequestException as e:
                raise IAError("Se ha cortado la conexión con Ollama.", f"Error de conexión con Ollama: {e}")
            contenido = _limpiar(contenido)
            if not llamadas:
                if not uso and not insistido and (intencion or AFIRMA.search(contenido)):
                    insistido = True                 # afirmo o debia actuar sin herramienta: corregir una vez
                    self.corregidas += 1
                    print(f"[IA] respuesta sin herramienta corregida: {contenido[:80]!r}")
                    extra = [{"role": "assistant", "content": contenido},
                             {"role": "user", "content": AVISO_SIN_HERRAMIENTA}]
                    continue
                if retener and on_texto and contenido:
                    decir(contenido)
                history.append({"role": "assistant", "content": contenido})
                return contenido or "No he sabido qué responder."
            uso, extra = True, []
            calls = []
            for i, c in enumerate(llamadas):
                f = c.get("function", {})
                calls.append({"id": f"call_{int(time.time() * 1000) % 10**8}_{i}",
                              "name": f.get("name", ""), "args": _args(f.get("arguments"))})
            history.append({"role": "assistant", "content": contenido, "tool_calls": calls})
            if on_texto and not dicho[0] and any(c["name"] in CONSULTAS for c in calls):
                decir(ESPERAS[int(time.time()) % len(ESPERAS)])     # que no haya silencio mientras busca
            resultados = []
            for c in calls:
                print(f"[herramienta] {c['name']} {c['args']}")
                res = self.run_tool(c["name"], c["args"])
                resultados.append(res)
                history.append({"role": "tool", "id": c["id"], "name": c["name"], "content": res})
            directa = confirmacion_directa(calls, resultados) if RESPUESTA_RAPIDA else None
            if directa:
                if on_texto:
                    decir(directa)
                history.append({"role": "assistant", "content": directa})
                return directa
        return "He hecho varias consultas pero no he llegado a una respuesta clara."

    def mantener_despierto(self):
        """Si la nube lleva INACTIVIDAD segundos sin usarse, le manda una peticion minima (1 token) para que
        la siguiente respuesta no tarde de mas. Devuelve True si la ha mandado."""
        if self._orden()[0] != "anthropic" or time.time() - self._ultimo_uso < INACTIVIDAD:
            return False
        self._ultimo_uso = time.time()
        try:
            self._cliente().messages.create(model=self.anthropic_model, max_tokens=1,
                                            messages=[{"role": "user", "content": "hola"}])
        except Exception:
            return False
        return True

    def velocidad(self):
        """Tokens por segundo de la ultima respuesta de Ollama (None si no hay datos)."""
        n, dur = self.stats.get("eval_count"), self.stats.get("eval_duration")
        return round(n / (dur / 1e9), 1) if n and dur else None

    def precalentar(self):
        """Carga el modelo en la grafica al arrancar y comprueba si cabe entero.
        Devuelve un texto para mostrar, o None."""
        if self._orden()[0] == "anthropic":
            t = time.time()
            try:      # abre la conexion con la nube para que la primera respuesta no tarde de mas
                self._cliente().messages.create(model=self.anthropic_model, max_tokens=1,
                                                messages=[{"role": "user", "content": "hola"}])
            except Exception as e:
                local = self._precalentar_ollama() if self.proveedor == "auto" else None
                return f"No he podido conectar con Claude al arrancar: {str(e)[:120]}" + (f" {local}" if local else "")
            self._ultimo_uso = time.time()
            return f"Claude listo ({time.time() - t:.1f} s)."
        return self._precalentar_ollama()

    def _precalentar_ollama(self):
        nombres = self.modelos_ollama(forzar=True)
        if not nombres:
            return None
        m = self.elegir_modelo_ollama(nombres)
        t = time.time()
        try:
            requests.post(f"{OLLAMA_URL}/api/generate", timeout=600,
                          json={"model": m, "prompt": "", "keep_alive": "30m", "options": {"num_ctx": _ctx(m)}})
        except requests.RequestException:
            return None
        carga = time.time() - t
        try:
            for x in requests.get(f"{OLLAMA_URL}/api/ps", timeout=5).json().get("models", []):
                if m in (x.get("name"), x.get("model")):
                    total, vram = x.get("size", 0), x.get("size_vram", 0)
                    if total and vram < total * 0.97:
                        return (f"Atención: {m} no cabe entero en la tarjeta gráfica (solo un "
                                f"{int(100 * vram / total)}% está en la GPU) y responderá lento. Cierra programas "
                                f"que usen la gráfica o pon OLLAMA_MODEL=granite4.1:8b en ajustes.env")
        except Exception:
            pass
        return f"Modelo {m} listo en la gráfica (cargado en {carga:.0f} s)."

    @staticmethod
    def _a_ollama(history):
        out = []
        for m in history:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                d = {"role": "assistant", "content": _con_fuentes(m)}
                if m.get("tool_calls"):
                    d["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["args"]}}
                                       for c in m["tool_calls"]]
                out.append(d)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_name": m["name"], "content": m["content"]})
        return out

    # ------------------------------------------------------------------ Anthropic
    def _hay_anthropic(self):
        return bool(self.anthropic_token if self.es_proxy else self.anthropic_key)

    def _proxy_responde(self):
        """True si el proxy (OmniRoute) acepta conexiones. Se comprueba en medio segundo y se recuerda 30 s."""
        momento, ok = self._proxy_estado
        if time.time() - momento < 30:
            return ok
        import socket
        from urllib.parse import urlparse
        u = urlparse(self.anthropic_base_url)
        try:
            with socket.create_connection((u.hostname or "localhost", u.port or (443 if u.scheme == "https" else 80)),
                                          timeout=0.5):
                ok = True
        except OSError:
            ok = False
        self._proxy_estado = (time.time(), ok)
        return ok

    def _cliente(self):
        if self._cliente_anthropic is None:
            import anthropic
            if self.es_proxy:
                # A traves del proxy: solo el token Bearer, sin enviar la clave real de Anthropic
                self._cliente_anthropic = anthropic.Anthropic(base_url=self.anthropic_base_url,
                                                              auth_token=self.anthropic_token)
            else:
                self._cliente_anthropic = anthropic.Anthropic(api_key=self.anthropic_key)
        return self._cliente_anthropic

    def _anthropic(self, history, on_texto=None, modelo=None):
        if not self._hay_anthropic():
            raise IAError("No tengo clave de Anthropic.",
                          "Falta ANTHROPIC_API_KEY en el archivo .env (o usa Ollama).")
        from anthropic import Timeout
        modelo = modelo or self.anthropic_model
        self.ultimo_modelo = modelo
        dicho = [False]

        def decir(t):
            dicho[0] = True
            on_texto(t)
        for _ in range(MAX_VUELTAS):
            emitido, acumulado = "", ""
            buscador = self.busqueda_nube and "claude" in modelo
            # con el buscador de Claude (todo internet), buscar_web (DuckDuckGo/Wikipedia) sobra
            tools = ([t for t in self.tools if t.get("name") != "buscar_web"] + [BUSQUEDA_CLAUDE]) if buscador \
                else self.tools
            try:
                with self._cliente().messages.stream(
                        model=modelo, max_tokens=1200, system=self.system_fn(), tools=tools,
                        messages=self._con_contexto(self._a_anthropic(history, crudo=buscador)),
                        timeout=Timeout(30.0, connect=ESPERA_PRIMER_TOKEN, read=ESPERA_PRIMER_TOKEN)) as st:
                    for ev in st:
                        if ev.type == "content_block_start" and \
                                getattr(ev.content_block, "type", "") == "server_tool_use":
                            if on_texto and not dicho[0]:     # Claude empieza a buscar: que no haya silencio
                                decir(ESPERAS[int(time.time()) % len(ESPERAS)])
                            continue
                        if ev.type != "text":
                            continue
                        trozo = ev.text
                        acumulado += trozo
                        if on_texto:
                            limpio = _limpiar_parcial(acumulado)
                            if len(limpio) > len(emitido) and limpio.startswith(emitido):
                                decir(limpio[len(emitido):])
                                emitido = limpio
                    resp = st.get_final_message()
                self._ultimo_uso = time.time()
            except Exception as e:
                txt = str(e)
                if buscador and "web_search" in txt and not emitido:
                    self.busqueda_nube = False             # este proveedor no tiene el buscador: seguir sin el
                    if self.on_reparacion:
                        self.on_reparacion("ia", f"el buscador de Claude no esta disponible ({txt[:80]}): uso buscar_web")
                    continue
                if "credit balance" in txt:
                    raise IAError("Tu cuenta de Anthropic no tiene saldo.",
                                  "La API de Anthropic no tiene saldo (la suscripción de claude.ai no lo incluye). "
                                  "Añade saldo en console.anthropic.com o usa OmniRoute.", permanente=True)
                if "401" in txt or "authentication" in txt.lower():
                    clave = "ANTHROPIC_AUTH_TOKEN (OmniRoute)" if self.es_proxy else "ANTHROPIC_API_KEY"
                    raise IAError("La clave de Anthropic no es válida.", f"{clave} no es válida.", permanente=True)
                raise IAError("No he podido conectar con Claude.", f"Error de Claude ({modelo}): {txt[:200]}")
            if self.on_externo and any(b.type == "server_tool_use" for b in resp.content):
                self.on_externo()                  # ha leido internet: mismas cautelas que con buscar_web
            texto = _MARCA_RE.sub("", "".join(b.text for b in resp.content if b.type == "text")).strip()
            usos = [b for b in resp.content if b.type == "tool_use"]
            extra = {}
            if f := _fuentes(resp.content):
                # la busqueda real se guarda tal cual: si solo quedara el texto, en el turno siguiente Claude ve
                # citas sin busqueda y cree que las ha inventado
                extra = {"busquedas": f, "nube": [_a_dict(b) for b in resp.content
                                                  if b.type in ("server_tool_use", "web_search_tool_result", "text")]}
            if resp.stop_reason != "tool_use" or not usos:
                if on_texto and texto and not emitido:
                    decir(texto)
                history.append({"role": "assistant", "content": texto, **extra})
                return texto
            calls = [{"id": b.id, "name": b.name, "args": dict(b.input)} for b in usos]
            history.append({"role": "assistant", "content": texto, "tool_calls": calls, **extra})
            if on_texto and not dicho[0] and any(c["name"] in CONSULTAS for c in calls):
                decir(ESPERAS[int(time.time()) % len(ESPERAS)])     # que no haya silencio mientras busca
            resultados = []
            for c in calls:
                print(f"[herramienta] {c['name']} {c['args']}")
                res = self.run_tool(c["name"], c["args"])
                resultados.append(res)
                history.append({"role": "tool", "id": c["id"], "name": c["name"], "content": res})
            directa = confirmacion_directa(calls, resultados) if RESPUESTA_RAPIDA else None
            if directa:
                if on_texto:
                    decir(directa)
                history.append({"role": "assistant", "content": directa})
                return directa
        return "He hecho varias consultas pero no he llegado a una respuesta clara."

    @staticmethod
    def _a_anthropic(history, crudo=False):
        """crudo=True: las busquedas de Claude se reenvian con sus bloques reales (solo si lleva el buscador)."""
        out = []
        for m in history:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                bloques = []
                if crudo and m.get("nube"):
                    bloques.extend(m["nube"])
                elif _con_fuentes(m):
                    bloques.append({"type": "text", "text": _con_fuentes(m)})
                for c in m.get("tool_calls", []):
                    bloques.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]})
                out.append({"role": "assistant", "content": bloques or [{"type": "text", "text": "..."}]})
            elif m["role"] == "tool":
                blk = {"type": "tool_result", "tool_use_id": m["id"], "content": m["content"]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(blk)
                else:
                    out.append({"role": "user", "content": [blk]})
        return out
