"""
Conversacion con Jarvis desde el movil (WhatsApp).

Seguridad: la IA solo ve las herramientas de PERMITIDAS | CON_CONFIRMACION. Las delicadas
(CON_CONFIRMACION) no se ejecutan cuando la IA las pide: se dejan pendientes y solo se ejecutan si
el SIGUIENTE mensaje del usuario es un "si", decidido por este codigo (antes_de_la_ia), no por la IA.
"""
import json
import time

import pc
import tareas

PERMITIDAS = {"guardar_nota", "anadir_al_diario", "buscar_en_cerebro", "leer_nota", "notas_recientes",
              "procesar_bandeja", "calendario_eventos", "correo_buscar", "correo_leer", "correo_borrador",
              "drive_buscar", "drive_leer", "buscar_web", "buscar_archivos", "leer_archivo", "listar_carpeta",
              "hora_actual", "whatsapp_recordar", "estado_tarea", "cancelar_tarea"}
CON_CONFIRMACION = {"correo_enviar", "calendario_crear", "drive_crear_documento", "encargar_tarea"}
_PROPIA = CON_CONFIRMACION - {"encargar_tarea"}      # encargar_tarea ya pide su confirmacion en tareas.py
CADUCA = 5 * 60                                      # segundos para confirmar
NO_DISPONIBLE = "Esa herramienta no está disponible por WhatsApp."
PROMPT_EXTRA = ("Hablas por WhatsApp: respuestas breves, sin abrir programas ni webs; "
                "el usuario no está delante del PC.")


def filtrar(tools):
    return [t for t in tools if t.get("name") in PERMITIDAS | CON_CONFIRMACION]


class Canal:
    def __init__(self, run_tool):
        self._run = run_tool
        self._pendiente = None          # {"nombre", "args", "momento"}

    def pendiente(self):
        if self._pendiente and time.time() - self._pendiente["momento"] > CADUCA:
            self._pendiente = None
        return self._pendiente

    def run_tool(self, nombre, args):
        if nombre not in PERMITIDAS | CON_CONFIRMACION:
            return NO_DISPONIBLE
        if nombre in _PROPIA:
            self._pendiente = {"nombre": nombre, "args": args, "momento": time.time()}
            return ("Pendiente de confirmación: resume al usuario exactamente lo que se va a hacer "
                    f"({nombre} con {json.dumps(args, ensure_ascii=False)}) y pídele que conteste sí.")
        if nombre == "encargar_tarea":      # desde el movil, una tarea siempre pide el "si" (aunque TAREAS_CONFIRMAR=0)
            args = {**args, "siempre_confirmar": True}
        return self._run(nombre, args)

    def antes_de_la_ia(self, texto):
        """Decide la confirmacion. Devuelve el texto a responder, o None para que siga la IA."""
        r = tareas.respuesta_confirmacion(texto, estricto=True)
        if r is not None:
            self._pendiente = None      # el mensaje ya se ha gastado en la tarea: nada queda armado
            return r
        p = self.pendiente()
        if not p:
            return None
        self._pendiente = None
        t = tareas.frase_normalizada(texto)
        if tareas.es_si_estricto(t):           # "vale, pero..." o "claro que no" no son un si
            return self._run(p["nombre"], p["args"])
        if tareas._NO.match(t):
            return "Vale, no lo hago."
        return None
