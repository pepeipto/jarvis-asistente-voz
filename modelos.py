"""
Prueba de modelos de Ollama para Jarvis: descarga los candidatos que falten y mide, con el prompt
y las herramientas reales de Jarvis, si eligen la herramienta correcta y a que velocidad.
Resultado en modelos.txt. Uso: modelos.bat / modelos.command  (o: python modelos.py modelo1 modelo2 ...)
No ejecuta ninguna herramienta (solo comprueba cual elegiria el modelo).
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
SALIDA = RAIZ / "modelos.txt"
OLLAMA = (os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
CANDIDATOS = sys.argv[1:] or ["qwen2.5:32b", "qwen3.8:27b", "granite4.1:8b"]

_f = open(SALIDA, "w", encoding="utf-8")


def out(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    _f.write(s + "\n")
    _f.flush()


PRUEBAS = [  # (pregunta, herramientas aceptadas; None = no debe usar herramienta)
    ("Apunta en el diario que mañana llamo a Marta a las diez.", {"anadir_al_diario", "guardar_nota"}),
    ("Guarda esta idea: hacer un canal de YouTube sobre inteligencia artificial para principiantes.", {"guardar_nota"}),
    ("¿Qué tengo apuntado sobre Marta?", {"buscar_en_cerebro"}),
    ("¿Qué hora es?", {"hora_actual"}),
    ("Abre la calculadora.", {"abrir_aplicacion"}),
    ("Cuéntame un chiste muy corto.", None),
    ("¿Qué he apuntado esta semana?", {"notas_recientes", "buscar_en_cerebro"}),
]


def descargar(m):
    tags = [x["name"] for x in requests.get(f"{OLLAMA}/api/tags", timeout=10).json().get("models", [])]
    if m in tags or f"{m}:latest" in tags:
        out(f"  {m}: ya descargado")
        return True
    out(f"  {m}: descargando...")
    ultimo = -10
    with requests.post(f"{OLLAMA}/api/pull", json={"model": m, "stream": True}, stream=True, timeout=None) as r:
        for linea in r.iter_lines():
            if not linea:
                continue
            d = json.loads(linea)
            if d.get("error"):
                out(f"  {m}: ERROR {d['error']}")
                return False
            if d.get("total") and d["total"] > 5e8:          # solo la parte grande (los pesos)
                pct = int(100 * d.get("completed", 0) / d["total"])
                if pct >= ultimo + 10 or pct < ultimo:
                    ultimo = pct
                    out(f"    {pct}% de {d['total'] / 1e9:.1f} GB")
            if d.get("status") == "success":
                out(f"  {m}: descargado")
                return True
    return True


def main():
    out(f"Prueba de modelos - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    import jarvis
    sistema = jarvis.SYSTEM_PROMPT_BASE.replace("@@FECHA@@", "jueves 16 de octubre de 2026, 00:30") \
        if "@@FECHA@@" in jarvis.SYSTEM_PROMPT_BASE else jarvis.system_prompt()
    tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                               "parameters": t["input_schema"]}} for t in jarvis.TOOLS]
    out("\n1. DESCARGAS")
    disponibles = [m for m in CANDIDATOS if descargar(m)]
    out("\n2. PRUEBAS (herramienta elegida / tiempo / velocidad)")
    resumen = []
    for m in disponibles:
        out(f"\n--- {m}")
        aciertos, tiempos, vel = 0, [], []
        for i, (q, esperado) in enumerate(PRUEBAS):
            cuerpo = {"model": m, "stream": False, "think": False, "keep_alive": "3m",
                      "options": {"temperature": 0.3, "num_ctx": 8192}, "tools": tools,
                      "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": q}]}
            t0 = time.time()
            try:
                r = requests.post(f"{OLLAMA}/api/chat", json=cuerpo, timeout=600)
            except Exception as e:
                out(f"  [{i}] error de conexion: {e}")
                continue
            dt = time.time() - t0
            if r.status_code != 200:
                out(f"  [{i}] HTTP {r.status_code}: {r.text[:160]}")
                continue
            d = r.json()
            msg = d.get("message", {})
            calls = [c.get("function", {}).get("name") for c in (msg.get("tool_calls") or [])]
            ok = (not calls) if esperado is None else bool(set(calls) & esperado)
            aciertos += ok
            if i > 0:
                tiempos.append(dt)            # la primera incluye la carga del modelo
            ev, evd = d.get("eval_count", 0), d.get("eval_duration", 1)
            if ev > 3:
                vel.append(ev / (evd / 1e9))
            texto = (msg.get("content") or "").strip().replace("\n", " ")
            out(f"  [{i}] {'OK ' if ok else 'MAL'} {dt:5.1f}s  herramientas={calls}  texto={texto[:90]!r}"
                + (f"  (carga {d.get('load_duration', 0) / 1e9:.1f}s)" if i == 0 else ""))
        gpu = ""
        try:
            for x in requests.get(f"{OLLAMA}/api/ps", timeout=10).json().get("models", []):
                if x["name"].startswith(m.split(":")[0]):
                    gpu = f"{x.get('size', 0) / 1e9:.1f} GB, {100 * x.get('size_vram', 0) / max(1, x.get('size', 1)):.0f}% en GPU"
        except Exception:
            pass
        media = sum(tiempos) / max(1, len(tiempos))
        v = sum(vel) / max(1, len(vel))
        out(f"  RESUMEN {m}: {aciertos}/{len(PRUEBAS)} aciertos | {media:.2f}s por respuesta | {v:.0f} tok/s | {gpu}")
        resumen.append((m, aciertos, media, v, gpu))
        requests.post(f"{OLLAMA}/api/generate", json={"model": m, "keep_alive": 0}, timeout=60)
        time.sleep(3)
    out("\n3. COMPARATIVA")
    for m, a, t, v, g in sorted(resumen, key=lambda x: (-x[1], x[2])):
        out(f"  {m:28s} {a}/{len(PRUEBAS)}  {t:5.2f}s  {v:5.0f} tok/s  {g}")
    out("\nFIN", time.strftime("%H:%M:%S"))


try:
    main()
except Exception as e:
    import traceback
    out("FALLO:", e)
    out(traceback.format_exc())
_f.close()
