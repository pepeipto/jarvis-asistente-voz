"""
REGISTRO DE ERRORES de Jarvis -> errores_log.txt
-------------------------------------------------
Cada fallo queda anotado con fecha, de donde viene, que paso y que hizo Jarvis para arreglarlo
(la "reparacion"). Asi se puede saber despues por que no respondia, aunque la consola ya este cerrada.
No se guardan correos, notas ni lo que dices: solo el tipo de fallo.
El archivo se rota solo al pasar de 1 MB (se guarda una copia errores_log.anterior.txt).
"""
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

ARCHIVO = Path(__file__).resolve().with_name("errores_log.txt")
ANTERIOR = ARCHIVO.with_name("errores_log.anterior.txt")
MAX_BYTES = 1_000_000
_lock = threading.Lock()


def _escribir(texto: str):
    with _lock:
        try:
            if ARCHIVO.exists() and ARCHIVO.stat().st_size > MAX_BYTES:
                ARCHIVO.replace(ANTERIOR)
            with ARCHIVO.open("a", encoding="utf-8") as f:
                f.write(texto)
        except OSError:
            pass                                  # el registro nunca debe tumbar a Jarvis


def error(origen: str, mensaje, reparacion: str = "", exc: BaseException = None):
    """Anota un fallo. origen: 'voz', 'ia', 'google'... reparacion: que hizo Jarvis al respecto."""
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} [{origen}] {mensaje}"
    if reparacion:
        linea += f" -> {reparacion}"
    linea += "\n"
    if exc is not None and exc.__traceback__ is not None:
        detalle = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-4:])
        linea += "    " + detalle.strip().replace("\n", "\n    ") + "\n"
    _escribir(linea)


def info(origen: str, mensaje: str):
    """Anota un evento normal importante (arranque, recuperacion completada...)."""
    _escribir(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{origen}] {mensaje}\n")


def ultimos(n: int = 20):
    """Ultimas n lineas principales del registro (sin los detalles tecnicos)."""
    try:
        lineas = [l for l in ARCHIVO.read_text(encoding="utf-8").splitlines() if l and not l.startswith("    ")]
        return lineas[-n:]
    except OSError:
        return []


def instalar_capturas():
    """Anota tambien los errores que nadie captura (en el programa principal y en los hilos)."""
    anterior = sys.excepthook

    def gancho(tipo, valor, tb):
        if not issubclass(tipo, KeyboardInterrupt):
            error("sin capturar", f"{tipo.__name__}: {valor}", exc=valor)
        anterior(tipo, valor, tb)

    def gancho_hilo(args):
        if args.exc_type is not SystemExit:
            nombre = args.thread.name if args.thread else "?"
            error("hilo " + nombre, f"{args.exc_type.__name__}: {args.exc_value}", exc=args.exc_value)

    sys.excepthook = gancho
    threading.excepthook = gancho_hilo
