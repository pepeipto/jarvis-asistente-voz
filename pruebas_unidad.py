"""
Pruebas rapidas de Jarvis, sin voz, sin red y sin tocar tus notas.
Uso:  venv\\Scripts\\python.exe -m unittest pruebas_unidad -v
(prueba_auto.py es la prueba completa de extremo a extremo con voz real)
"""
import unittest
from types import SimpleNamespace

import llm


# ---------------------------------------------------------------- cliente falso de Anthropic
class _Stream:
    def __init__(self, trozos, bloques, stop):
        self.trozos, self.bloques, self.stop = trozos, bloques, stop

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        return iter(self.trozos)

    def get_final_message(self):
        return SimpleNamespace(content=self.bloques, stop_reason=self.stop)


def _texto(t):
    return SimpleNamespace(type="text", text=t)


def _uso(nombre, args, id_="tu_1"):
    return SimpleNamespace(type="tool_use", name=nombre, input=args, id=id_)


class ClienteFalso:
    """guion: {modelo: [respuesta, ...]}; cada respuesta es una excepcion o (trozos, bloques, stop_reason)."""

    def __init__(self, guion):
        self.guion = {m: list(r) for m, r in guion.items()}
        self.llamadas = []
        self.messages = self

    def stream(self, **kw):
        self.llamadas.append(kw)
        r = self.guion[kw["model"]].pop(0)
        if isinstance(r, Exception):
            raise r
        return _Stream(*r)

    def create(self, **kw):
        self.llamadas.append(kw)
        return SimpleNamespace(content=[_texto(".")], stop_reason="end_turn")


def _ia(cliente, proveedor="auto", run_tool=None):
    ia = llm.IA([], lambda: "sistema", run_tool or (lambda n, a: "ok"), proveedor=proveedor,
                anthropic_model="cc/claude-haiku-5-5", anthropic_base_url="http://omniroute", anthropic_token="t")
    ia._cliente_anthropic = cliente
    ia._ollama = lambda h, on_texto=None: (_ for _ in ()).throw(AssertionError("no debia usar Ollama"))
    return ia


class CerebroNube(unittest.TestCase):
    def test_stream_emite_trozos(self):
        c = ClienteFalso({"cc/claude-haiku-5-5": [(["Hola. ", "Qué tal."], [_texto("Hola. Qué tal.")], "end_turn")]})
        ia, dicho = _ia(c), []
        texto = ia.responder([{"role": "user", "content": "hola"}], on_texto=dicho.append)
        self.assertEqual(texto, "Hola. Qué tal.")
        self.assertEqual("".join(dicho), "Hola. Qué tal.")
        self.assertGreaterEqual(len(dicho), 2)          # habla por trozos, no al final
        self.assertEqual(ia.activo, "anthropic")

    def test_herramienta_y_respuesta(self):
        c = ClienteFalso({"cc/claude-haiku-5-5": [
            ([], [_uso("hora_actual", {})], "tool_use"),
            (["Son las cinco."], [_texto("Son las cinco.")], "end_turn")]})
        usadas = []
        ia = _ia(c, run_tool=lambda n, a: usadas.append(n) or "17:00")
        hist = [{"role": "user", "content": "qué hora es"}]
        self.assertEqual(ia.responder(hist), "Son las cinco.")
        self.assertEqual(usadas, ["hora_actual"])
        self.assertTrue(any(m.get("tool_calls") for m in hist))
        self.assertTrue(any(m["role"] == "tool" for m in hist))

    def test_stream_con_tiempo_maximo(self):
        c = ClienteFalso({"cc/claude-haiku-5-5": [(["ok"], [_texto("ok")], "end_turn")]})
        _ia(c).responder([{"role": "user", "content": "hola"}])
        self.assertIn("timeout", c.llamadas[0])
        self.assertLessEqual(c.llamadas[0]["timeout"].read, 4)

    def test_respaldo_gratis_en_429(self):
        c = ClienteFalso({"cc/claude-haiku-5-5": [RuntimeError("Error code: 429 - rate limit")],
                          "auto/best-free": [(["Gratis."], [_texto("Gratis.")], "end_turn")]})
        ia = _ia(c)
        self.assertEqual(ia.responder([{"role": "user", "content": "hola"}]), "Gratis.")
        self.assertEqual(ia.activo, "anthropic_gratis")

    def test_respaldo_gratis_si_tarda(self):
        c = ClienteFalso({"cc/claude-haiku-5-5": [TimeoutError("Request timed out")],
                          "auto/best-free": [(["Gratis."], [_texto("Gratis.")], "end_turn")]})
        self.assertEqual(_ia(c).responder([{"role": "user", "content": "hola"}]), "Gratis.")

    def test_respaldo_ollama_sin_red(self):
        c = ClienteFalso({"cc/claude-haiku-5-5": [ConnectionError("refused")],
                          "auto/best-free": [ConnectionError("refused")]})
        ia = _ia(c)
        ia._ollama = lambda h, on_texto=None: "local"
        self.assertEqual(ia.responder([{"role": "user", "content": "hola"}]), "local")
        self.assertEqual(ia.activo, "ollama")

    def test_sin_nube_usa_ollama(self):
        ia = llm.IA([], lambda: "s", lambda n, a: "ok", proveedor="auto")
        ia._ollama = lambda h, on_texto=None: "local"
        self.assertEqual(ia.responder([{"role": "user", "content": "hola"}]), "local")

    def test_precalentar_nube_no_toca_ollama(self):
        c = ClienteFalso({})
        ia = _ia(c)
        ia.modelos_ollama = lambda forzar=False: (_ for _ in ()).throw(AssertionError("no debia mirar Ollama"))
        self.assertIn("Claude listo", ia.precalentar())
        self.assertEqual(c.llamadas[0]["max_tokens"], 1)


if __name__ == "__main__":
    unittest.main()
