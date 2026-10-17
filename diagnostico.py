"""
Diagnostico de Jarvis: mide todo y lo guarda en diagnostico.txt (nunca escribe claves).
Se lanza con diagnostico.bat. No reproduce sonido.
"""
import io
import json
import os
import platform
import subprocess
import sys
import time
import traceback
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "diagnostico.txt"
_f = open(SALIDA, "w", encoding="utf-8")


def out(*a):
    linea = " ".join(str(x) for x in a)
    print(linea)
    _f.write(linea + "\n")
    _f.flush()


def seccion(t):
    out("")
    out("=" * 70)
    out(t)
    out("=" * 70)


def paso(nombre, fn):
    try:
        fn()
    except Exception as e:
        out(f"[FALLO en {nombre}] {type(e).__name__}: {e}")
        out(traceback.format_exc()[-800:])


out(f"Diagnostico de Jarvis - {time.strftime('%Y-%m-%d %H:%M:%S')}")

try:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
    load_dotenv(RAIZ / "ajustes.env")    # igual que jarvis.py: .env manda, ajustes.env completa
except Exception as e:
    out("No se pudo cargar .env:", e)

sys.path.insert(0, str(RAIZ))


def env(n, d=""):
    v = os.getenv(n, d).strip().strip('"').strip("'")
    return "" if "..." in v else v


import requests  # noqa: E402

OLLAMA = (os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
EL_KEY = env("ELEVENLABS_API_KEY")
VOICE = env("ELEVENLABS_VOICE_ID")


# ---------------------------------------------------------------- 1. sistema
def sistema():
    seccion("1. SISTEMA")
    out("Python:", sys.version.split()[0], "|", platform.platform())
    for mod in ("anthropic", "numpy", "sounddevice", "requests", "pypdf", "docx", "dotenv"):
        try:
            m = __import__(mod)
            out(f"  {mod:12s} OK  {getattr(m, '__version__', '')}")
        except Exception as e:
            out(f"  {mod:12s} FALTA ({e})")
    out("Configuracion (.env, sin claves):")
    for n in ("LLM_PROVEEDOR", "OLLAMA_MODEL", "STT_MODE", "INTERFAZ", "WAKE_WORD", "ELEVENLABS_TTS_MODEL", "CLAUDE_MODEL"):
        out(f"  {n} = {env(n) or '(vacio)'}")
    out("  ANTHROPIC_API_KEY:", "configurada" if env("ANTHROPIC_API_KEY") else "no")
    out("  ELEVENLABS_API_KEY:", "configurada" if EL_KEY else "no", "| VOICE_ID:", "configurado" if VOICE else "no")


# ---------------------------------------------------------------- 2. GPU
def gpu():
    seccion("2. TARJETA GRAFICA")
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,driver_version",
                            "--format=csv,noheader"], capture_output=True, text=True, timeout=20)
        out(r.stdout.strip() or r.stderr.strip())
        r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        out("Procesos usando la GPU (computo):")
        out(r.stdout.strip() or "  (ninguno)")
    except FileNotFoundError:
        out("nvidia-smi no encontrado")


# ---------------------------------------------------------------- 3. Ollama
modelos = []


def ollama():
    seccion("3. OLLAMA")
    try:
        out("Version:", requests.get(f"{OLLAMA}/api/version", timeout=5).json())
    except Exception as e:
        out("Ollama NO responde:", e)
        return
    tags = requests.get(f"{OLLAMA}/api/tags", timeout=10).json().get("models", [])
    out("Modelos instalados:")
    for m in tags:
        det = m.get("details", {})
        out(f"  {m['name']:32s} {m.get('size', 0) / 1e9:6.1f} GB  {det.get('parameter_size', '')} {det.get('quantization_level', '')}")
        if "embed" not in m["name"].lower():
            modelos.append(m["name"])
    ps = requests.get(f"{OLLAMA}/api/ps", timeout=10).json().get("models", [])
    out("Cargados ahora en memoria:")
    for m in ps:
        tam, vram = m.get("size", 0), m.get("size_vram", 0)
        out(f"  {m['name']}: {tam / 1e9:.1f} GB, en GPU {vram / 1e9:.1f} GB ({100 * vram / max(1, tam):.0f}%)")
    if not ps:
        out("  (ninguno)")


def bench():
    seccion("4. VELOCIDAD REAL DE CADA MODELO (con el prompt y herramientas de Jarvis)")
    if not modelos:
        out("No hay modelos que probar.")
        return
    try:
        import jarvis  # usa el prompt y las herramientas reales
        sistema_txt = jarvis.system_prompt()
        tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                   "parameters": t["input_schema"]}} for t in jarvis.herramientas()]
    except Exception as e:
        out("No se pudo importar jarvis.py:", e)
        sistema_txt, tools = "Eres Jarvis. Responde en español.", []
    preguntas = [
        "Hola Jarvis, ¿cómo estás? Responde en una frase.",
        "Apunta en el diario que mañana llamo a Marta a las diez.",
    ]
    for m in modelos:
        out(f"\n--- {m}")
        for k, q in enumerate(preguntas):
            cuerpo = {"model": m, "stream": False, "think": False, "keep_alive": "2m",
                      "options": {"temperature": 0.4, "num_ctx": 8192},
                      "messages": [{"role": "system", "content": sistema_txt}, {"role": "user", "content": q}]}
            if tools:
                cuerpo["tools"] = tools
            t0 = time.time()
            r = requests.post(f"{OLLAMA}/api/chat", json=cuerpo, timeout=600)
            dt = time.time() - t0
            if r.status_code != 200:
                out(f"  [{k}] HTTP {r.status_code}: {r.text[:200]}")
                if "tools" in r.text.lower() and "tools" in cuerpo:
                    out("  (este modelo NO admite herramientas)")
                break
            d = r.json()
            ns = 1e9
            ev, evd = d.get("eval_count", 0), d.get("eval_duration", 1)
            pe, ped = d.get("prompt_eval_count", 0), d.get("prompt_eval_duration", 1)
            msg = d.get("message", {})
            calls = [c.get("function", {}).get("name") for c in (msg.get("tool_calls") or [])]
            out(f"  [{k}] total {dt:5.1f}s | carga {d.get('load_duration', 0) / ns:5.1f}s | "
                f"prompt {pe} tok a {pe / max(1e-9, ped / ns):7.0f} tok/s | genera {ev} tok a {ev / max(1e-9, evd / ns):5.1f} tok/s")
            out(f"       respuesta: {(msg.get('content') or '').strip()[:140]!r} herramientas: {calls}")
        try:
            ps = requests.get(f"{OLLAMA}/api/ps", timeout=10).json().get("models", [])
            for x in ps:
                if x["name"] == m:
                    tam, vram = x.get("size", 0), x.get("size_vram", 0)
                    out(f"  memoria: {tam / 1e9:.1f} GB total, {vram / 1e9:.1f} GB en GPU ({100 * vram / max(1, tam):.0f}% GPU)")
            requests.post(f"{OLLAMA}/api/generate", json={"model": m, "keep_alive": 0}, timeout=60)  # liberar VRAM
        except Exception as e:
            out("  (no se pudo leer /api/ps)", e)


# ---------------------------------------------------------------- 5. ElevenLabs
def elevenlabs():
    seccion("5. ELEVENLABS")
    if not EL_KEY:
        out("Sin clave.")
        return
    h = {"xi-api-key": EL_KEY}
    r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers=h, timeout=15)
    if r.status_code == 200:
        s = r.json()
        out(f"Plan: {s.get('tier')} | caracteres usados {s.get('character_count')} de {s.get('character_limit')}")
    else:
        out("Suscripcion: HTTP", r.status_code, r.text[:200])
    if VOICE:
        r = requests.get(f"https://api.elevenlabs.io/v1/voices/{VOICE}", headers=h, timeout=15)
        if r.status_code == 200:
            v = r.json()
            out(f"Voz: {v.get('name')} | categoria: {v.get('category')}")
        else:
            out("Voz: HTTP", r.status_code, r.text[:200])
    frase = "Sistemas en línea. A su servicio, señor."
    pcm_guardado = None
    for modelo in ("eleven_flash_v2_5", "eleven_multilingual_v2"):
        t0 = time.time()
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/stream", params={"output_format": "pcm_24000"},
                          headers={**h, "Content-Type": "application/json"},
                          json={"text": frase, "model_id": modelo}, stream=True, timeout=30)
        if r.status_code != 200:
            out(f"TTS {modelo}: HTTP {r.status_code} {r.text[:200]}")
            continue
        primero, datos = None, b""
        for ch in r.iter_content(4096):
            if primero is None:
                primero = time.time() - t0
            datos += ch
        out(f"TTS {modelo}: primer audio en {primero:.2f}s, total {time.time() - t0:.2f}s, {len(datos) / 48000:.1f}s de voz")
        pcm_guardado = pcm_guardado or datos
    if pcm_guardado:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm_guardado)
        t0 = time.time()
        r = requests.post("https://api.elevenlabs.io/v1/speech-to-text", headers=h,
                          data={"model_id": "scribe_v2", "language_code": "es"},
                          files={"file": ("p.wav", buf.getvalue(), "audio/wav")}, timeout=60)
        if r.status_code == 200:
            out(f"STT scribe_v2: {time.time() - t0:.2f}s -> {r.json().get('text')!r}")
        else:
            out(f"STT: HTTP {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------- 6. audio
def audio():
    seccion("6. AUDIO (solo mide nivel, no graba nada)")
    import sounddevice as sd
    import numpy as np
    out("Dispositivo de entrada por defecto:", sd.query_devices(kind="input")["name"])
    out("Dispositivo de salida por defecto:", sd.query_devices(kind="output")["name"])
    x = sd.rec(int(1.5 * 16000), samplerate=16000, channels=1, dtype="int16")
    sd.wait()
    rms = float(np.sqrt(np.mean((x.astype(np.float32) / 32768) ** 2)))
    out(f"Nivel de ruido ambiente: {rms:.4f} (umbral de Jarvis seria {max(0.01, rms * 3):.4f})")


# ---------------------------------------------------------------- 7. cerebro
def cerebro():
    seccion("7. SEGUNDO CEREBRO")
    import memoria
    memoria.iniciar()
    out("Carpeta:", memoria.BASE)
    out("Estadisticas:", memoria.estadisticas())


# ---------------------------------------------------------------- 8. claude code
def claude_code():
    seccion("8. CLAUDE CODE (tareas grandes)")
    import subprocess
    import tareas
    exe = tareas.ejecutable()
    if not exe:
        out("No instalado. Instalalo con: npm install -g @anthropic-ai/claude-code")
        return
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
    out("Ejecutable:", exe)
    out("Version:", (r.stdout or r.stderr).strip())


# ---------------------------------------------------------------- 9. whatsapp
def _enmascarar(n):
    n = "".join(c for c in n if c.isdigit())
    return n if len(n) < 6 else n[:2] + "*" * (len(n) - 5) + n[-3:]


def whatsapp_diag():
    seccion("9. WHATSAPP")
    import whatsapp
    variables = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_MI_NUMERO", "WHATSAPP_APP_SECRET",
                 "WHATSAPP_VERIFY_TOKEN", "NGROK_DOMINIO")
    faltan = [n for n in variables if not env(n)]
    for n in variables:
        out(f"  {n}: {'puesta' if env(n) else 'FALTA'}")
    if env("WHATSAPP_MI_NUMERO"):
        out("  Tu numero (enmascarado):", _enmascarar(env("WHATSAPP_MI_NUMERO")))
    if faltan:
        out("Faltan variables en .env:", ", ".join(faltan), "(mira LEEME.md, seccion WhatsApp)")
    token, phone = env("WHATSAPP_TOKEN"), env("WHATSAPP_PHONE_ID")
    version = env("WHATSAPP_API_VERSION") or whatsapp.API_VERSION_DEFECTO
    base = f"https://graph.facebook.com/{version}"
    cab = {"Authorization": f"Bearer {token}"}

    def error_meta(r):
        try:
            return r.json().get("error", {}).get("message", "") or r.text[:150]
        except ValueError:
            return r.text[:150]

    if token and phone:
        try:
            r = requests.get(f"{base}/{phone}", headers=cab, timeout=10,
                             params={"fields": "display_phone_number,verified_name"})
            if r.status_code == 200:
                d = r.json()
                out(f"Token y numero de Jarvis: OK ({d.get('verified_name', '?')}, "
                    f"{_enmascarar(str(d.get('display_phone_number', '')))})")
            else:
                out(f"Token y numero de Jarvis: ERROR HTTP {r.status_code}: {error_meta(r)}")
        except Exception as e:
            out("Token y numero de Jarvis: no se pudo comprobar:", type(e).__name__)
    else:
        out("Token y numero de Jarvis: sin comprobar (faltan WHATSAPP_TOKEN o WHATSAPP_PHONE_ID)")

    plantilla = env("WHATSAPP_PLANTILLA") or whatsapp.PLANTILLA_DEFECTO
    waba = env("WHATSAPP_WABA_ID")
    if waba and token:
        try:
            r = requests.get(f"{base}/{waba}/message_templates", headers=cab, timeout=10,
                             params={"name": plantilla, "fields": "name,status,language"})
            if r.status_code == 200:
                datos = r.json().get("data", [])
                if datos:
                    out(f"Plantilla {plantilla}: " + ", ".join(f"{t.get('language')} {t.get('status')}" for t in datos))
                else:
                    out(f"Plantilla {plantilla}: NO existe en esa cuenta")
            else:
                out(f"Plantilla {plantilla}: ERROR HTTP {r.status_code}: {error_meta(r)}")
        except Exception as e:
            out("Plantilla: no se pudo comprobar:", type(e).__name__)
    else:
        out(f"Plantilla {plantilla}: sin comprobar (opcional: pon WHATSAPP_WABA_ID en .env para comprobarla)")

    exe = whatsapp.buscar_ngrok()
    out("ngrok.exe:", exe or "NO encontrado (instalalo como explica LEEME.md)")
    out("ngrok publicando tu dominio ahora:", "si" if whatsapp.ngrok_ya_publica() else "no (Jarvis lo arranca al abrirse)")
    dominio = whatsapp._dominio_ngrok()
    if dominio:
        try:
            r = requests.get(f"https://{dominio}/whatsapp", params={"hub.mode": "x"}, timeout=10)
            out(f"Dominio {dominio}: responde (HTTP {r.status_code})")
        except Exception as e:
            out(f"Dominio {dominio}: sin respuesta ({type(e).__name__}); normal si Jarvis o ngrok no estan abiertos")
    else:
        out("Dominio: sin comprobar (falta NGROK_DOMINIO)")


for nombre, fn in (("sistema", sistema), ("gpu", gpu), ("ollama", ollama), ("bench", bench),
                   ("elevenlabs", elevenlabs), ("audio", audio), ("cerebro", cerebro),
                   ("claude_code", claude_code), ("whatsapp", whatsapp_diag)):
    paso(nombre, fn)
seccion("FIN")
out(time.strftime("%H:%M:%S"))
_f.close()
