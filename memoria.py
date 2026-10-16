"""
SEGUNDO CEREBRO de Jarvis
-------------------------
- Todo se guarda como archivos Markdown normales (tuyos, legibles, sin depender de nada).
- Un indice de busqueda (SQLite FTS5) permite encontrar cosas rapido. El indice se puede
  borrar (indice.db) y se reconstruye solo: la fuente de verdad son los archivos.

Estructura de la carpeta cerebro/:
  inbox/       <- suelta aqui PDFs, Word, txt o md para que Jarvis los aprenda
  notas/       <- notas que Jarvis guarda cuando se lo pides
  diario/      <- una nota por dia con capturas rapidas
  documentos/  <- documentos importados (texto extraido) + originales/
"""
import os
import re
import shutil
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(os.getenv("CEREBRO_DIR") or (Path(__file__).resolve().parent / "cerebro")).resolve()
NOTAS = BASE / "notas"
DIARIO = BASE / "diario"
INBOX = BASE / "inbox"
DOCS = BASE / "documentos"
ORIGINALES = DOCS / "originales"
DB = BASE / "indice.db"
CARPETAS_INDEXADAS = (NOTAS, DIARIO, DOCS)

MAX_CHUNK = 900          # caracteres por fragmento indexado
MAX_LECTURA = 6000       # caracteres maximos que se devuelven al leer una nota

STOPWORDS = set("""
de la que el en y a los del se las por un para con una su al lo como mas pero sus le ya o este si
porque esta entre cuando muy sin sobre tambien me hasta hay donde quien desde todo nos durante todos
uno les ni contra otros ese eso ante ellos e esto mi antes algunos unos yo otro otras otra tanto esa
estos mucho nada muchos cual poco ella estar estas algunas algo mis tu te ti tus fue ser es son he
has ha dime dame cual cuales que cuanto cuanta cuando como donde apunta nota notas
""".split())


# ------------------------------------------------------------------ utilidades
def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _slug(s: str, maximo: int = 50) -> str:
    s = _sin_acentos(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:maximo].strip("-")) or "sin-titulo"


def _rel(path: Path) -> str:
    return path.resolve().relative_to(BASE).as_posix()


def _archivos_md():
    """Todas las notas .md del cerebro (incluidas las creadas desde Obsidian en cualquier carpeta),
    ignorando carpetas ocultas (.obsidian, .trash), la bandeja de entrada y los originales."""
    for p in BASE.rglob("*.md"):
        partes = p.relative_to(BASE).parts
        if any(x.startswith(".") for x in partes):
            continue
        if partes[0] == "inbox" or partes[:2] == ("documentos", "originales"):
            continue
        yield p


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS meta(path TEXT PRIMARY KEY, mtime REAL)")
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
        "path UNINDEXED, title UNINDEXED, text, tokenize='unicode61 remove_diacritics 2')"
    )
    return con


def _trocear(texto: str):
    """Divide un texto en fragmentos de ~MAX_CHUNK caracteres respetando parrafos."""
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    actual = ""
    for p in parrafos:
        while len(p) > MAX_CHUNK:  # parrafo gigante: cortarlo
            if actual:
                yield actual
                actual = ""
            yield p[:MAX_CHUNK]
            p = p[MAX_CHUNK:]
        if len(actual) + len(p) + 2 > MAX_CHUNK and actual:
            yield actual
            actual = p
        else:
            actual = f"{actual}\n\n{p}" if actual else p
    if actual:
        yield actual


def _titulo(texto: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", texto, re.M)
    return m.group(1).strip() if m else fallback


def _indexar(con: sqlite3.Connection, path: Path):
    rel = _rel(path)
    texto = path.read_text(encoding="utf-8", errors="replace")
    titulo = _titulo(texto, path.stem)
    cuerpo = re.sub(r"\A---\n.*?\n---\n", "", texto, count=1, flags=re.S)  # quitar cabecera
    con.execute("DELETE FROM chunks WHERE path=?", (rel,))
    for trozo in _trocear(cuerpo):
        con.execute("INSERT INTO chunks(path,title,text) VALUES(?,?,?)", (rel, titulo, trozo))
    con.execute("INSERT OR REPLACE INTO meta(path,mtime) VALUES(?,?)", (rel, path.stat().st_mtime))


def reindexar() -> int:
    """Pone el indice al dia (archivos nuevos/cambiados/borrados). Devuelve cuantos se reindexaron."""
    con = _db()
    existentes = {_rel(p): p for p in _archivos_md()}
    en_indice = dict(con.execute("SELECT path, mtime FROM meta"))
    n = 0
    for rel, p in existentes.items():
        if en_indice.get(rel) != p.stat().st_mtime:
            _indexar(con, p)
            n += 1
    for rel in set(en_indice) - set(existentes):
        con.execute("DELETE FROM chunks WHERE path=?", (rel,))
        con.execute("DELETE FROM meta WHERE path=?", (rel,))
        n += 1
    con.commit()
    con.close()
    return n


def iniciar() -> None:
    for c in (NOTAS, DIARIO, INBOX, DOCS, ORIGINALES):
        c.mkdir(parents=True, exist_ok=True)
    leeme = BASE / "LEEME.txt"
    if not leeme.exists():
        leeme.write_text(
            "SEGUNDO CEREBRO DE JARVIS\n\n"
            "inbox/      Suelta aqui PDFs, Word, txt o md. Jarvis los lee y los aprende.\n"
            "notas/      Notas que Jarvis guarda cuando se lo pides.\n"
            "diario/     Una nota por dia.\n"
            "documentos/ Documentos ya importados.\n\n"
            "Abre esta carpeta como 'vault' en Obsidian (gratis) para ver tus notas como una red.\n"
            "Puedes editar o borrar cualquier archivo .md: Jarvis lo detecta solo.\n",
            encoding="utf-8",
        )
    reindexar()


# ------------------------------------------------------------------ herramientas
def guardar_nota(titulo: str, contenido: str, etiquetas: list | None = None) -> str:
    ahora = datetime.now()
    base = f"{ahora:%Y-%m-%d}-{_slug(titulo)}"
    path = NOTAS / f"{base}.md"
    i = 2
    while path.exists():
        path = NOTAS / f"{base}-{i}.md"
        i += 1
    tags = ", ".join(_slug(t) for t in (etiquetas or []))
    path.write_text(
        f"---\ntitulo: {titulo}\nfecha: {ahora:%Y-%m-%d %H:%M}\ntags: [{tags}]\n---\n\n"
        f"# {titulo}\n\n{contenido.strip()}\n",
        encoding="utf-8",
    )
    con = _db()
    _indexar(con, path)
    con.commit()
    con.close()
    return f"Nota guardada: {_rel(path)}"


def anadir_al_diario(texto: str) -> str:
    ahora = datetime.now()
    path = DIARIO / f"{ahora:%Y-%m-%d}.md"
    if not path.exists():
        path.write_text(f"# Diario {ahora:%Y-%m-%d}\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- {ahora:%H:%M} {texto.strip()}\n")
    con = _db()
    _indexar(con, path)
    con.commit()
    con.close()
    return f"Anotado en el diario de hoy ({_rel(path)})"


def _consulta_fts(consulta: str) -> str:
    palabras = re.findall(r"[a-z0-9ñ]+", _sin_acentos(consulta).lower())
    terminos = []
    for w in palabras:
        if w in STOPWORDS or len(w) < 2:
            continue
        # recorte simple para atrapar plurales/conjugaciones en español (reuniones -> reunio*)
        terminos.append(f'"{w[:-2]}"*' if len(w) >= 6 else f'"{w}"')
    return " OR ".join(terminos)


def buscar(consulta: str, limite: int = 5) -> str:
    q = _consulta_fts(consulta)
    if not q:
        return "La consulta no contiene palabras utiles para buscar."
    reindexar()
    con = _db()
    try:
        filas = con.execute(
            "SELECT path, title, snippet(chunks, 2, '[', ']', '...', 30), bm25(chunks) "
            "FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT 40",
            (q,),
        ).fetchall()
    except sqlite3.OperationalError as e:
        return f"Error de busqueda: {e}"
    finally:
        con.close()
    vistos, salida = set(), []
    for path, titulo, frag, _ in filas:
        if path in vistos:
            continue
        vistos.add(path)
        salida.append(f"- {titulo} ({path}): {frag}")
        if len(salida) >= max(1, min(limite, 10)):
            break
    return "\n".join(salida) if salida else "No he encontrado nada relacionado en el cerebro."


def leer_nota(ruta: str) -> str:
    p = (BASE / ruta).resolve()
    if BASE not in p.parents or p.suffix != ".md" or not p.is_file() \
            or any(x.startswith(".") for x in p.relative_to(BASE).parts):
        return "Ruta no valida: solo puedo leer notas .md dentro del cerebro."
    t = p.read_text(encoding="utf-8", errors="replace")
    return t[:MAX_LECTURA] + ("\n[...recortado...]" if len(t) > MAX_LECTURA else "")


def notas_recientes(dias: int = 7) -> str:
    limite = datetime.now() - timedelta(days=max(1, dias))
    items = []
    for p in _archivos_md():
        m = datetime.fromtimestamp(p.stat().st_mtime)
        if m >= limite:
            items.append((m, p))
    items.sort(reverse=True)
    if not items:
        return f"No hay notas nuevas en los ultimos {dias} dias."
    out = []
    for m, p in items[:15]:
        t = _titulo(p.read_text(encoding="utf-8", errors="replace"), p.stem)
        out.append(f"- {m:%d/%m %H:%M} {t} ({_rel(p)})")
    return "\n".join(out)


def _extraer_texto(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    if ext == ".docx":
        from docx import Document
        d = Document(str(p))
        return "\n\n".join(par.text for par in d.paragraphs if par.text.strip())
    raise ValueError(f"formato {ext or '?'} no soportado (usa pdf, docx, txt o md)")


def estadisticas() -> dict:
    """Numero de notas y las 5 mas recientes (para los paneles de la ventana)."""
    items = []
    for p in _archivos_md():
        items.append((p.stat().st_mtime, p))
    items.sort(reverse=True)
    ahora = datetime.now().timestamp()
    recientes = []
    for mt, p in items[:5]:
        t = _titulo(p.read_text(encoding="utf-8", errors="replace")[:600], p.stem)
        seg = max(0, ahora - mt)
        hace = "ahora" if seg < 90 else f"{int(seg // 60)} min" if seg < 3600 else \
            f"{int(seg // 3600)} h" if seg < 86400 else f"{int(seg // 86400)} d"
        recientes.append({"titulo": t, "hace": hace})
    return {"notas": len(items), "recientes": recientes}


def procesar_inbox() -> str:
    archivos = [f for f in INBOX.iterdir() if f.is_file()]
    if not archivos:
        return "La bandeja de entrada esta vacia."
    ok, fallos = [], []
    con = _db()
    for f in archivos:
        try:
            texto = _extraer_texto(f).strip()
            if len(texto) < 20:
                raise ValueError("no contiene texto legible (¿es un escaneo/imagen?)")
            ahora = datetime.now()
            destino = DOCS / f"{ahora:%Y-%m-%d}-{_slug(f.stem)}.md"
            i = 2
            while destino.exists():
                destino = DOCS / f"{ahora:%Y-%m-%d}-{_slug(f.stem)}-{i}.md"
                i += 1
            destino.write_text(
                f"---\ntitulo: {f.stem}\nfecha: {ahora:%Y-%m-%d %H:%M}\norigen: {f.name}\n---\n\n"
                f"# {f.stem}\n\n{texto}\n",
                encoding="utf-8",
            )
            shutil.move(str(f), str(ORIGINALES / f.name))
            _indexar(con, destino)
            ok.append(f.name)
        except Exception as e:
            fallos.append(f"{f.name}: {e}")
    con.commit()
    con.close()
    partes = []
    if ok:
        partes.append(f"Importados {len(ok)}: " + ", ".join(ok))
    if fallos:
        partes.append("No se pudieron importar: " + "; ".join(fallos))
    return ". ".join(partes)


# ------------------------------------------------------------------ definicion para Claude
HERRAMIENTAS = [
    {
        "name": "guardar_nota",
        "description": "Guarda una nota permanente en el segundo cerebro del usuario (ideas, decisiones, datos, "
                       "resumenes). Usala cuando pida apuntar, recordar o guardar algo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Titulo corto y descriptivo"},
                "contenido": {"type": "string", "description": "Contenido completo, claro y autocontenido. Enlaza "
                              "personas, proyectos, lugares y temas con [[Nombre]] (estilo Obsidian)."},
                "etiquetas": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["titulo", "contenido"],
        },
    },
    {
        "name": "anadir_al_diario",
        "description": "Anade una linea rapida al diario de hoy (capturas breves, tareas, sucesos del dia).",
        "input_schema": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]},
    },
    {
        "name": "buscar_en_cerebro",
        "description": "Busca en las notas, el diario y los documentos del usuario. Usala SIEMPRE antes de "
                       "responder preguntas sobre su pasado, sus proyectos, personas, decisiones o documentos. "
                       "Si no hay resultados, prueba con sinonimos o palabras clave distintas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "Palabras clave"},
                "limite": {"type": "integer", "description": "Maximo de resultados (por defecto 5)"},
            },
            "required": ["consulta"],
        },
    },
    {
        "name": "leer_nota",
        "description": "Lee el contenido completo de una nota usando la ruta devuelta por buscar_en_cerebro.",
        "input_schema": {"type": "object", "properties": {"ruta": {"type": "string"}}, "required": ["ruta"]},
    },
    {
        "name": "notas_recientes",
        "description": "Lista las notas y documentos modificados en los ultimos N dias (para resumenes y repasos).",
        "input_schema": {"type": "object", "properties": {"dias": {"type": "integer"}}},
    },
    {
        "name": "procesar_bandeja",
        "description": "Importa al cerebro los archivos (pdf, docx, txt, md) que el usuario ha dejado en la bandeja inbox.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def ejecutar(nombre: str, args: dict):
    """Ejecuta una herramienta del cerebro. Devuelve None si el nombre no es del cerebro."""
    if nombre == "guardar_nota":
        return guardar_nota(args["titulo"], args["contenido"], args.get("etiquetas"))
    if nombre == "anadir_al_diario":
        return anadir_al_diario(args["texto"])
    if nombre == "buscar_en_cerebro":
        return buscar(args["consulta"], int(args.get("limite") or 5))
    if nombre == "leer_nota":
        return leer_nota(args["ruta"])
    if nombre == "notas_recientes":
        return notas_recientes(int(args.get("dias") or 7))
    if nombre == "procesar_bandeja":
        return procesar_inbox()
    return None
