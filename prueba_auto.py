"""
Prueba automatica de Jarvis de principio a fin, en SILENCIO (no suena nada por los altavoces).

Para cada pregunta:
  1. ElevenLabs genera la pregunta con voz (como si hablaras al microfono).
  2. Jarvis la transcribe (igual que con tu voz real).
  3. La IA responde (con herramientas) en streaming.
  4. Se genera la voz de la respuesta y se "reproduce" en silencio, animando la ventana 3D.
Mide cada paso y comprueba que lo que se pide apuntar se guarda de verdad.
Usa un cerebro de pruebas aparte (prueba_cerebro/), asi que no toca tus notas.
Resultado en prueba_auto.txt.   Uso: prueba_auto.bat / prueba_auto.command   (con --sin-ventana no abre la ventana 3D)
"""
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
import time as _t
os.environ["CEREBRO_DIR"] = str(RAIZ / "prueba_cerebro" / _t.strftime("%Y%m%d-%H%M%S"))   # cerebro nuevo en cada prueba
os.environ["JARVIS_MUDO"] = "1"
sys.path.insert(0, str(RAIZ))

import numpy as np  # noqa: E402
import requests  # noqa: E402

import jarvis  # noqa: E402
import memoria  # noqa: E402

SALIDA = RAIZ / "prueba_auto.txt"
_f = open(SALIDA, "w", encoding="utf-8")


def out(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    _f.write(s + "\n")
    _f.flush()


PREGUNTAS = [
    # (lo que "dices", comprobacion: texto que debe aparecer en el cerebro despues, o None)
    ("Jarvis, hola, ¿qué tal estás?", None),
    ("Jarvis, apunta en el diario que el viernes tengo dentista a las cinco.", "dentista"),
    ("Jarvis, ¿qué tengo apuntado para el viernes?", None),
    ("Jarvis, guarda esta idea: montar un canal sobre inteligencia artificial para principiantes.", "canal"),
    ("Jarvis, ¿qué hora es?", None),
    ("Jarvis, ¿qué ideas he guardado?", None),
]


def voz_de_prueba(texto):
    """Genera la pregunta con voz (16 kHz) usando ElevenLabs, como si fuera el microfono."""
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{jarvis.VOICE_ID}",
                      params={"output_format": "pcm_16000"},
                      headers={"xi-api-key": jarvis.ELEVEN_KEY, "Content-Type": "application/json"},
                      json={"text": texto, "model_id": "eleven_flash_v2_5", "language_code": "es"}, timeout=30)
    r.raise_for_status()
    return np.frombuffer(r.content, dtype=np.int16).astype(np.float32) / 32768.0


def texto_cerebro():
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in memoria._archivos_md()).lower()


def prueba(ui_web):
    try:
        jarvis.cargar_audio()
    except Exception as e:
        out("Aviso audio:", e)
    jarvis.ia = jarvis.crear_ia()
    out(f"Prueba automatica - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out("IA:", jarvis.ia.describir(), "| voz:", jarvis.TTS_MODEL, "| transcripcion:", jarvis.STT_MODE)
    t = time.time()
    msg = jarvis.ia.precalentar()
    out(f"Precarga del modelo: {time.time() - t:.1f}s -> {msg}")
    history, filas = [], []
    for frase, comprobar in PREGUNTAS:
        out("\n>>", frase)
        try:
            audio = voz_de_prueba(frase)
        except Exception as e:
            out("  no se pudo generar la voz de prueba:", e)
            continue
        jarvis.ui.set_estado("escuchando")
        if not jarvis.STT_VIVO:
            for k in range(0, len(audio), 1600):                     # animar el orbe como si hablaras
                jarvis.ui.set_nivel(min(1.0, float(np.sqrt(np.mean(audio[k:k + 1600] ** 2))) / 0.12))
                time.sleep(0.1 if ui_web else 0)
        modo = "normal"
        texto = None
        if jarvis.STT_VIVO:
            # como el microfono real: enviar la voz en trozos de 30 ms mientras "hablas" + 0,7 s de silencio
            pcm = (np.clip(np.concatenate([audio, np.zeros(int(0.7 * 16000), np.float32)]), -1, 1) * 32767).astype(np.int16)
            tv = jarvis.TranscripcionVivo()
            for k in range(0, len(pcm), 480):
                tv.enviar(pcm[k:k + 480])
                time.sleep(0.03)
            t_fin_habla = time.time()
            jarvis.ui.set_estado("pensando")
            texto = tv.terminar()
            if texto is not None:
                modo = "en vivo"
            else:
                out(f"  (en vivo fallo: {tv.error}; uso la normal)")
        if texto is None:
            t_fin_habla = time.time()
            jarvis.ui.set_estado("pensando")
            try:
                texto = jarvis.transcribe(None, audio)
            except Exception as e:
                out("  error al transcribir:", e)
                continue
        t_stt = time.time() - t_fin_habla
        activo, resto = jarvis.strip_wake(texto)
        query = resto if activo else texto
        out(f"  transcrito {modo} ({t_stt:.2f}s): {texto!r} -> activacion={'si' if activo else 'NO'}")
        n_hist = len(history)
        with jarvis.lock_cerebro:
            jarvis.ui.log("tu", query)
            t0 = time.time()
            h = jarvis.Habla()
            resp = jarvis.responder(history, query, on_texto=h.alimentar)
            if not h.texto.strip():
                h.alimentar(resp)
            t_ia = time.time() - t0
            h.terminar()
        herramientas = [c["name"] for m in history[n_hist:] for c in m.get("tool_calls", [])]
        primer_audio = (t_stt + h.t_primer_audio) if h.t_primer_audio is not None else None
        ok = ""
        if comprobar:
            ok = "GUARDADO OK" if comprobar in texto_cerebro() else "NO SE GUARDO"
        out(f"  respuesta: {resp!r}")
        out(f"  herramientas: {herramientas} {ok}")
        out(f"  tiempos: transcribir {t_stt:.2f}s | IA primer texto {h.t_primer_texto or 0:.2f}s | "
            f"IA completa {t_ia:.2f}s | EMPIEZA A HABLAR {primer_audio or 0:.2f}s tras callarte"
            + (f" | {jarvis.ia.velocidad()} tok/s" if jarvis.ia.velocidad() else ""))
        filas.append((frase, primer_audio, ok))
        time.sleep(1.5)
    out("\nRESUMEN")
    validos = [p for _, p, _ in filas if p]
    if validos:
        out(f"  Tiempo hasta que empieza a hablar: media {sum(validos) / len(validos):.2f}s, "
            f"peor {max(validos):.2f}s, mejor {min(validos):.2f}s")
    out(f"  Respuestas corregidas por no usar herramienta: {jarvis.ia.corregidas}")
    fallos = [f for f, _, ok in filas if ok == "NO SE GUARDO"]
    out("  Guardado:", "todo correcto" if not fallos else f"FALLOS en {fallos}")
    fps = getattr(jarvis.ui, "fps", None)
    if fps is not None:
        out(f"  Fluidez de la ventana 3D: {fps:.0f} fotogramas/s")
    out("FIN", time.strftime("%H:%M:%S"))


def main():
    memoria.iniciar()
    con_ventana = "--sin-ventana" not in sys.argv
    if con_ventana:
        from interfaz_web import OrbeWeb
        jarvis.ui = OrbeWeb(info=jarvis.datos_ui)

        def hilo():
            time.sleep(6)                      # dar tiempo a que se abra la ventana
            try:
                prueba(True)
            except Exception as e:
                import traceback
                out("FALLO:", e, traceback.format_exc())
            time.sleep(4)
            jarvis.ui.cerrar()
        threading.Thread(target=hilo, daemon=True).start()
        jarvis.ui.run()
    else:
        prueba(False)
    _f.close()
    os._exit(0)


if __name__ == "__main__":
    main()
