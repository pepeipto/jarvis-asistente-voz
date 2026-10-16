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


class ManosPC(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        from pathlib import Path
        import pc
        self.pc, self.os = pc, os
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis_prueba_")).resolve()
        self._antes = os.environ.get("CARPETAS_PERMITIDAS")
        os.environ["CARPETAS_PERMITIDAS"] = str(self.tmp)

    def tearDown(self):
        import shutil
        if self._antes is None:
            self.os.environ.pop("CARPETAS_PERMITIDAS", None)
        else:
            self.os.environ["CARPETAS_PERMITIDAS"] = self._antes
        self.os.system(f'rmdir "{self.tmp / "enlace"}" 2>nul')
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ruta_alias(self):
        self.os.environ.pop("CARPETAS_PERMITIDAS")
        r = self.pc.ruta_segura("descargas")
        self.assertTrue(r.is_dir())
        self.assertIn(r.name.lower(), ("downloads", "descargas"))
        self.assertEqual(self.pc.ruta_segura("en la carpeta de Descargas"), r)

    def test_ruta_fuera_rechazada(self):
        (self.tmp / ".env").write_text("CLAVE=1")
        for mala in (str(self.tmp / ".." / "x"), r"C:\Windows\win.ini", str(self.tmp / ".env")):
            with self.assertRaises(PermissionError, msg=mala):
                self.pc.ruta_segura(mala)

    def test_junction_fuera_rechazada(self):
        self.os.system(f'mklink /J "{self.tmp / "enlace"}" "C:\\Windows" >nul')
        self.assertTrue((self.tmp / "enlace").exists())
        with self.assertRaises(PermissionError):
            self.pc.ruta_segura(str(self.tmp / "enlace" / "win.ini"))

    def test_ruta_relativa_dentro_de_permitidas(self):
        (self.tmp / "Proyectos").mkdir()
        self.assertEqual(self.pc.ruta_segura("Proyectos"), self.tmp / "Proyectos")

    def test_buscar_archivos(self):
        (self.tmp / "clientes" / "2026").mkdir(parents=True)
        (self.tmp / "clientes" / "2026" / "informe García.pdf").write_bytes(b"%PDF")
        (self.tmp / "node_modules").mkdir()
        (self.tmp / "node_modules" / "informe garcia.js").write_text("x")
        r = self.pc.ejecutar("buscar_archivos", {"texto": "garcia"})
        self.assertIn("informe García.pdf", r)
        self.assertNotIn("node_modules", r)

    def test_leer_txt_latin1_y_recorte(self):
        f = self.tmp / "notas.txt"
        f.write_bytes(("Año y canción. " * 1400).encode("latin-1"))
        r = self.pc.ejecutar("leer_archivo", {"ruta": str(f)})
        self.assertIn("Año y canción.", r)
        self.assertIn("recortado", r)
        self.assertLessEqual(len(r), 8200)

    def test_leer_binario(self):
        f = self.tmp / "datos.xlsx"
        f.write_bytes(b"PK\x03\x04\x00\x00binario\x00\x01")
        r = self.pc.ejecutar("leer_archivo", {"ruta": str(f)})
        self.assertIn("No puedo leer ese tipo de archivo", r)

    def test_listar_carpeta(self):
        for i in range(60):
            (self.tmp / f"f{i:02d}.txt").write_text("x")
        r = self.pc.ejecutar("listar_carpeta", {"ruta": str(self.tmp)})
        self.assertIn("f00.txt", r)
        self.assertNotIn("f59.txt", r)
        self.assertIn("60", r)                       # dice cuantos hay en total

    def test_programa_normaliza(self):
        indice = {"microsoft excel": "x.lnk", "word": "w.lnk"}
        self.assertEqual(self.pc._buscar_programa("excél", indice), "x.lnk")
        self.assertEqual(self.pc._buscar_programa("Excel", indice), "x.lnk")
        self.assertIsNone(self.pc._buscar_programa("photoshop", indice))

    def test_herramienta_ajena(self):
        self.assertIsNone(self.pc.ejecutar("hora_actual", {}))


HTML_DDG = """
<div class="result results_links"><h2 class="result__title">
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.aemet.es%2Fmadrid&amp;rut=x">El Tiempo: <b>Madrid</b></a></h2>
<a class="result__snippet" href="x">Predicción para <b>mañana</b>: 23 &#176;C y lluvia.</a></div>
<div class="result results_links"><h2 class="result__title">
<a rel="nofollow" class="result__a" href="https://www.tiempo.com/madrid">Tiempo en Madrid</a></h2>
<a class="result__snippet" href="y">Máxima 22, mínima 11.</a></div>
"""


class BusquedaWeb(unittest.TestCase):
    def test_analiza_resultados(self):
        import web
        r = web._analizar(HTML_DDG)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["url"], "https://www.aemet.es/madrid")       # enlace de redireccion resuelto
        self.assertEqual(r[0]["titulo"], "El Tiempo: Madrid")
        self.assertIn("23 °C", r[0]["fragmento"])

    def test_formato_resultados(self):
        import web
        web.buscar, antes = (lambda c, maximo=5: web._analizar(HTML_DDG)), web.buscar
        try:
            t = web.ejecutar("buscar_web", {"consulta": "tiempo madrid"})
        finally:
            web.buscar = antes
        self.assertIn("El Tiempo: Madrid", t)
        self.assertIn("https://www.tiempo.com/madrid", t)

    def test_sin_resultados(self):
        import web
        web.buscar, antes = (lambda c, maximo=5: []), web.buscar
        try:
            self.assertIn("No he encontrado nada", web.ejecutar("buscar_web", {"consulta": "zzz"}))
        finally:
            web.buscar = antes

    def test_herramienta_ajena(self):
        import web
        self.assertIsNone(web.ejecutar("hora_actual", {}))


if __name__ == "__main__":
    unittest.main()
