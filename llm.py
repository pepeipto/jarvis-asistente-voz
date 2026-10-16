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
CTX = int(os.getenv("OLLAMA_CTX") or 0)    # 0 = automatico (8192, o 6144 en modelos de 30B o mas)


RESPUESTA_RAPIDA = (os.getenv("RESPUESTA_RAPIDA") or "1") != "0"
CONSULTAS = {"buscar_en_cerebro", "leer_nota", "notas_recientes", "procesar_bandeja",
             "calendario_eventos", "correo_buscar", "correo_leer", "drive_buscar", "drive_leer"}
ESPERAS = ["Déjame mirar. ", "Un momento. ", "Lo compruebo. "]


def confirmacion_directa(calls, resultados):
    """Si solo se usaron herramientas de 'hacer' (guardar, abrir...) y todo fue bien, devuelve una
    confirmacion corta sin pedirle otra vuelta a la IA (ahorra ~1 s). Si no, None."""
    frases = []
    for c, res in zip(calls, resultados):
        if res.lower().startswith(("error", "no conozco", "ruta no valida", "no se pudo")):
            return None
        n = c["name"]
        if n == "anadir_al_diario":
            frases.append("Anotado en tu diario.")
        elif n == "guardar_nota":
            t = (c["args"].get("titulo") or "").strip()
            frases.append(f"Guardado en tus notas: {t}." if t else "Guardado en tus notas.")
        elif n == "abrir_aplicacion":
            frases.append(f"Abriendo {c['args'].get('nombre', 'la aplicación')}.")
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

    def __init__(self, hablado, detalle):
        super().__init__(detalle)
        self.hablado = hablado
        self.detalle = detalle


def _limpiar(texto):
    """Quita bloques <think>...</think> que algunos modelos locales incluyen."""
    return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()


def _limpiar_parcial(texto):
    """Version de _limpiar para texto que aun se esta generando."""
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    i = t.find("<think>")
    return (t[:i] if i != -1 else t).lstrip()


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
                 proveedor="auto", ollama_model="", contexto_fn=None):
        self.tools = tools                    # herramientas en formato Anthropic (input_schema)
        self.system_fn = system_fn
        self.run_tool = run_tool
        self.anthropic_key = anthropic_key
        self.anthropic_model = anthropic_model
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
        self.on_reparacion = None              # funcion(origen, texto) para anotar autorreparaciones

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
        if self.proveedor in ("auto", "ollama"):
            nombres = self.modelos_ollama()
            if nombres:
                m = self.elegir_modelo_ollama(nombres)
                if m:
                    return f"Ollama · {m}"
            if self.proveedor == "ollama":
                return "Ollama (sin conexión)" if nombres is None else "Ollama (sin modelos)"
        if self.anthropic_key and self.proveedor in ("auto", "anthropic"):
            return f"Claude · {self.anthropic_model}"
        return "Sin IA configurada"

    # ------------------------------------------------------------------ punto de entrada
    def responder(self, history, on_texto=None):
        """Genera la respuesta (ejecutando herramientas si hace falta). Modifica history.
        on_texto(trozo) recibe el texto a medida que se genera (para empezar a hablar antes)."""
        orden = {"ollama": ["ollama"], "anthropic": ["anthropic"]}.get(self.proveedor, ["ollama", "anthropic"])
        errores = []
        for prov in orden:
            n_antes = len(history)
            try:
                if prov == "ollama":
                    texto = self._ollama(history, on_texto)
                else:
                    texto = self._anthropic(history)
                    if on_texto and texto:
                        on_texto(texto)
                self.activo = prov
                return texto
            except IAError as e:
                errores.append(e)
                del history[n_antes:]              # deshacer lo que haya dejado a medias
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

    def velocidad(self):
        """Tokens por segundo de la ultima respuesta de Ollama (None si no hay datos)."""
        n, dur = self.stats.get("eval_count"), self.stats.get("eval_duration")
        return round(n / (dur / 1e9), 1) if n and dur else None

    def precalentar(self):
        """Carga el modelo en la grafica al arrancar y comprueba si cabe entero.
        Devuelve un texto para mostrar, o None."""
        if self.proveedor == "anthropic":
            return None
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
                d = {"role": "assistant", "content": m.get("content", "")}
                if m.get("tool_calls"):
                    d["tool_calls"] = [{"function": {"name": c["name"], "arguments": c["args"]}}
                                       for c in m["tool_calls"]]
                out.append(d)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_name": m["name"], "content": m["content"]})
        return out

    # ------------------------------------------------------------------ Anthropic
    def _cliente(self):
        if self._cliente_anthropic is None:
            import anthropic
            self._cliente_anthropic = anthropic.Anthropic(api_key=self.anthropic_key)
        return self._cliente_anthropic

    def _anthropic(self, history):
        if not self.anthropic_key:
            raise IAError("No tengo clave de Anthropic.",
                          "Falta ANTHROPIC_API_KEY en el archivo .env (o usa Ollama).")
        for _ in range(MAX_VUELTAS):
            try:
                resp = self._cliente().messages.create(
                    model=self.anthropic_model, max_tokens=800, system=self.system_fn(),
                    tools=self.tools, messages=self._con_contexto(self._a_anthropic(history)))
            except Exception as e:
                txt = str(e)
                if "credit balance" in txt:
                    raise IAError("Tu cuenta de Anthropic no tiene saldo.",
                                  "La API de Anthropic no tiene saldo (la suscripción de claude.ai no lo incluye). "
                                  "Añade saldo en console.anthropic.com o usa Ollama.")
                if "401" in txt or "authentication" in txt.lower():
                    raise IAError("La clave de Anthropic no es válida.", "ANTHROPIC_API_KEY no es válida.")
                raise IAError("No he podido conectar con Claude.", f"Error de Anthropic: {txt[:200]}")
            texto = "".join(b.text for b in resp.content if b.type == "text").strip()
            usos = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not usos:
                history.append({"role": "assistant", "content": texto})
                return texto
            calls = [{"id": b.id, "name": b.name, "args": dict(b.input)} for b in usos]
            history.append({"role": "assistant", "content": texto, "tool_calls": calls})
            for c in calls:
                print(f"[herramienta] {c['name']} {c['args']}")
                history.append({"role": "tool", "id": c["id"], "name": c["name"],
                                "content": self.run_tool(c["name"], c["args"])})
        return "He hecho varias consultas pero no he llegado a una respuesta clara."

    @staticmethod
    def _a_anthropic(history):
        out = []
        for m in history:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                bloques = []
                if m.get("content"):
                    bloques.append({"type": "text", "text": m["content"]})
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
