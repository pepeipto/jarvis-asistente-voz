"""Pequenas diferencias entre Windows y macOS (y Linux) en un solo sitio."""
import sys

ES_WINDOWS = sys.platform.startswith("win")
ES_MAC = sys.platform == "darwin"


def script(nombre):
    """Nombre del script de ayuda segun el sistema: script('instalar') -> instalar.bat | instalar.command"""
    return nombre + (".bat" if ES_WINDOWS else ".command")
