# Jarvis v1.5 — Cerebro en la nube y manos en el PC: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jarvis usa Claude Haiku vía OmniRoute como cerebro (con streaming y respaldos), abre programas/carpetas, busca y lee archivos, busca en la web y encarga tareas grandes a Claude Code con confirmación por voz.

**Architecture:** Se mantiene el patrón de módulos de herramientas (`HERRAMIENTAS` + `ejecutar(nombre, args)` que devuelve `None` si la herramienta no es suya). Nuevos módulos: `pc.py` (programas, carpetas, archivos), `web.py` (búsqueda), `tareas.py` (Claude Code en segundo plano). `llm.py` cambia el orden de proveedores y pasa Anthropic a streaming. La confirmación de tareas la decide `jarvis.responder` antes de llamar a la IA.

**Tech Stack:** Python 3 (venv del proyecto), anthropic SDK 1.15, requests, pypdf, python-docx, `unittest` de la biblioteca estándar (no hay pytest), Node 24 + `@anthropic-ai/claude-code`.

**Spec:** `docs/superpowers/specs/2026-10-16-jarvis-nube-y-manos-design.md`

## Global Constraints
- Cerebro por defecto: `cc/claude-haiku-5-5` (`CLAUDE_MODEL` en `.env`, que tiene prioridad sobre `ajustes.env`).
- Orden con `LLM_PROVEEDOR=auto`: anthropic (modelo principal) → anthropic con `auto/best-free` → ollama con `OLLAMA_MODEL_RESPALDO` (por defecto `granite4.1:8b`).
- Cambio a `auto/best-free` si error 429/límite o si no llega el primer token en 4 s.
- Ollama no se precalienta al inicio cuando hay nube configurada.
- Rutas: `Path.resolve()` y pertenencia a `CARPETAS_PERMITIDAS`; prohibidos siempre `C:\Windows`, `Program Files`, `Program Files (x86)`, `ProgramData`, `AppData`, `.ssh`, `.env`, `.git`.
- `leer_archivo`: máx. 8000 caracteres; `listar_carpeta`: máx. 50 entradas; `buscar_archivos`: máx. 3 s.
- Claude Code: `--allowedTools` Read, Glob, Grep, Edit, Write, WebSearch, WebFetch, `Bash(git status:*)`, `Bash(git diff:*)`, `Bash(git log:*)`; nunca `--dangerously-skip-permissions`; tiempo máximo 15 min; una tarea a la vez; carpeta por defecto `Documentos\Jarvis\tareas`.
- Resultados de `leer_archivo`, `buscar_web`, `correo_leer`, `drive_leer` se envuelven en `<contenido_no_fiable origen="...">…</contenido_no_fiable>`.
- Textos hablados en español, cortos, sin markdown. Comentarios del código en español sin tildes, como el código actual.
- Pruebas: `venv\Scripts\python.exe -m unittest pruebas_unidad -v` (archivo nuevo en la raíz).

## Review Focus
- Nombre de programa con tildes o mayúsculas distintas ("Excel", "excél", "word") → se abre igual (normalizar con `memoria._sin_acentos` y minúsculas). Test en Tarea 2.
- Ruta dicha por voz relativa o con alias ("descargas", "en documentos") → se resuelve a la carpeta real, no a la carpeta de trabajo de Jarvis. Test en Tarea 2.
- Archivo binario o con codificación rara (.xlsx, latin-1) → mensaje claro, sin excepción ni basura. Test en Tarea 2.
- Respuesta "sí" con palabra de activación o puntuación ("Jarvis, sí, adelante.") → confirma; cualquier otra cosa cancela la tarea pendiente. Test en Tarea 4.
- OmniRoute caído (puerto cerrado) → respuesta de Ollama respaldo, no excepción. Test en Tarea 1.

---

### Task 1: Cerebro en la nube con streaming y respaldos

**Files:**
- Modify: `llm.py` (`IA.__init__`, `responder`, `_anthropic`, `precalentar`, `describir`)
- Modify: `jarvis.py` (`crear_ia`, lectura de `OLLAMA_MODEL_RESPALDO`)
- Modify: `.env` (`CLAUDE_MODEL=cc/claude-haiku-5-5`), `ajustes.env` (`OLLAMA_MODEL_RESPALDO=granite4.1:8b`)
- Create: `pruebas_unidad.py`

**Interfaces:**
- Produces: `IA(..., modelo_respaldo_nube="auto/best-free")`; `IA._anthropic(history, on_texto=None, modelo=None) -> str`; orden de `responder` con `auto` = `["anthropic", "anthropic_gratis", "ollama"]`.

- [ ] **Step 1: Tests en `pruebas_unidad.py`** con un cliente falso que imita `messages.stream` (context manager con `text_stream`, `get_final_message()` que devuelve bloques `text`/`tool_use` y `stop_reason`):
  - `test_stream_emite_trozos`: dos trozos "Hola. " y "Qué tal." → `on_texto` recibe ambos en orden; devuelve "Hola. Qué tal.".
  - `test_herramienta_y_respuesta`: primera vuelta `tool_use` (`hora_actual`), segunda texto → `run_tool` llamado una vez, historia contiene `tool_calls` y `tool`.
  - `test_respaldo_gratis_en_429`: el cliente lanza excepción con "429" para `cc/claude-haiku-5-5` y responde para `auto/best-free` → texto del gratuito, `ia.activo == "anthropic_gratis"`.
  - `test_respaldo_ollama_sin_red`: cliente lanza `ConnectionError` siempre y `_ollama` parcheado devuelve "local" → "local".
- [ ] **Step 2:** Ejecutar `venv\Scripts\python.exe -m unittest pruebas_unidad -v` → FAIL.
- [ ] **Step 3: Implementar.** `_anthropic` usa `self._cliente().messages.stream(...)`; por cada trozo, mismo troceo que Ollama (`_limpiar_parcial` sobre lo acumulado, emitir lo nuevo); `get_final_message()` para `tool_use`. Reutilizar `confirmacion_directa` y `ESPERAS` igual que en `_ollama`. Si el primer token no llega en 4 s → `IAError` (para pasar al gratuito). `precalentar` con nube: `messages.create(max_tokens=1)` y devolver `"Claude listo (x,x s)."`; no tocar Ollama. `describir` muestra el modelo principal. `responder` ya no llama `on_texto(texto)` al final para anthropic (lo hace el streaming).
- [ ] **Step 4:** Tests → PASS. Prueba real: `venv\Scripts\python.exe jarvis.py --texto` con "hola" y "qué hora es" (sin las variables `ANTHROPIC_*` heredadas: `env -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_API_KEY`).
- [ ] **Step 5: Commit** `v1.5: cerebro en la nube (Haiku via OmniRoute) con streaming y respaldos`.

### Task 2: `pc.py` — programas, carpetas y archivos

**Files:**
- Create: `pc.py`
- Modify: `jarvis.py` (añadir `pc.HERRAMIENTAS` a `TOOLS`, `pc.ejecutar` en `_run_tool`, quitar `abrir_aplicacion` de `TOOLS` dejando `APPS` como alias dentro de `pc`), `llm.py` (`confirmacion_directa`: `abrir_programa`, `abrir_carpeta`; `CONSULTAS`: `buscar_archivos`, `leer_archivo`, `listar_carpeta`)
- Modify: `pruebas_unidad.py`

**Interfaces:**
- Produces: `pc.carpetas_permitidas() -> list[Path]`; `pc.ruta_segura(texto: str) -> Path` (lanza `PermissionError`/`FileNotFoundError`); `pc.indexar_programas() -> dict[str, str]`; herramientas `abrir_programa(nombre)`, `abrir_carpeta(ruta)`, `buscar_archivos(texto, carpeta="", maximo=10)`, `leer_archivo(ruta)`, `listar_carpeta(ruta)`; `pc.ejecutar(nombre, args) -> str | None`.

- [ ] **Step 1: Tests** (carpeta temporal fijada con `CARPETAS_PERMITIDAS=<tmp>`):
  - `test_ruta_alias`: `ruta_segura("descargas")` → `Path.home()/"Downloads"` (o la carpeta conocida de Windows).
  - `test_ruta_fuera_rechazada`: `<tmp>\..\x`, `C:\Windows\win.ini`, `<tmp>\.env` → `PermissionError`.
  - `test_junction_fuera_rechazada`: junction dentro de `<tmp>` hacia `C:\Windows` (`mklink /J`) → `PermissionError`.
  - `test_buscar_archivos`: crea `informe García.pdf` en subcarpeta → `buscar_archivos("garcia")` lo encuentra; ignora `node_modules`.
  - `test_leer_txt_latin1_y_recorte`: archivo latin-1 de 20 000 caracteres → texto legible, ≤ 8000 caracteres + aviso de recorte.
  - `test_leer_binario`: `.xlsx` falso → mensaje "no puedo leer ese tipo de archivo" sin excepción.
  - `test_programa_normaliza`: índice `{"microsoft excel": "x.lnk"}` → `_buscar_programa("excél")` → `"x.lnk"`.
- [ ] **Step 2:** Tests → FAIL.
- [ ] **Step 3: Implementar.** Alias: escritorio, documentos, descargas, imágenes, música, vídeos, onedrive (carpetas reales con `os.path.expanduser` y la variable `OneDrive`). Omitir archivos con atributos `FILE_ATTRIBUTE_OFFLINE` (0x1000) o `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` (0x400000) mediante `os.stat().st_file_attributes`. Índice de programas: `.lnk` de `%APPDATA%\Microsoft\Windows\Start Menu\Programs` y `%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs`, al importar en hilo; apps de la tienda con `powershell Get-StartApps | ConvertTo-Json` en ese mismo hilo, abiertas con `explorer shell:AppsFolder\<AppID>`. Abrir con `os.startfile`. Coincidencia: normalizar, luego "contiene", luego `difflib.get_close_matches(cutoff=0.6)`.
- [ ] **Step 4:** Tests → PASS; prueba real en modo texto: "abre el bloc de notas", "abre descargas", "busca archivos que se llamen informe".
- [ ] **Step 5: Commit** `v1.5: Jarvis abre cualquier programa y lee archivos del PC`.

### Task 3: `web.py` — búsqueda web

**Files:**
- Create: `web.py`
- Modify: `jarvis.py` (`TOOLS`, `_run_tool`), `llm.py` (`CONSULTAS` += `buscar_web`), `pruebas_unidad.py`

**Interfaces:**
- Produces: herramienta `buscar_web(consulta)`; `web.buscar(consulta, maximo=5) -> list[dict(titulo, fragmento, url)]`; `web.ejecutar(nombre, args) -> str | None`.

- [ ] **Step 1: Sondeo** (una vez): probar los modelos `duckduckgo-web` de OmniRoute con `/v1/chat/completions`. Si devuelven resultados con URL en < 3 s, usar esa vía; si no, `POST https://html.duckduckgo.com/html/` con `q=` y parsear `a.result__a` / `.result__snippet` con `re`/`html.parser`. Anotar la vía elegida en el docstring de `web.py`.
- [ ] **Step 2: Test** `test_formato_resultados`: con `web.buscar` parcheado devolviendo 2 resultados → texto con títulos y URLs, envuelto en `<contenido_no_fiable origen="web">`. Test `test_sin_resultados` → "No he encontrado nada".
- [ ] **Step 3:** Tests → FAIL; implementar; tests → PASS; prueba real "busca en internet el tiempo en Madrid mañana".
- [ ] **Step 4: Commit** `v1.5: busqueda web`.

### Task 4: `tareas.py` — encargar tareas a Claude Code con confirmación

**Files:**
- Create: `tareas.py`
- Modify: `jarvis.py` (`TOOLS`, `_run_tool`, `responder` intercepta la confirmación, aviso hablado al terminar), `instalar.bat` y `diagnostico.py` (comprobar `claude --version`), `pruebas_unidad.py`

**Interfaces:**
- Produces: herramientas `encargar_tarea(descripcion, carpeta="")`, `estado_tarea()`, `cancelar_tarea()`; `tareas.pendiente() -> dict | None`; `tareas.respuesta_confirmacion(texto: str) -> str | None` (None si no hay pendiente); `tareas.on_fin: Callable[[str], None]`; `tareas.comando(descripcion, carpeta) -> list[str]`.

- [ ] **Step 1: Tests:**
  - `test_encargar_queda_pendiente`: `encargar_tarea("ordena descargas")` → no lanza proceso; devuelve texto que pide confirmar y repite la tarea; `pendiente()` no es None.
  - `test_confirmar_si`: con pendiente, `respuesta_confirmacion("Jarvis, sí, adelante.")` → "Me pongo con ello…" y se llama al lanzador (parcheado).
  - `test_confirmar_otra_cosa_cancela`: "no, espera" y "qué hora es" → cancela; con "qué hora es" devuelve None para que la IA responda normalmente.
  - `test_comando`: contiene `-p`, `--output-format json`, `--allowedTools` con las herramientas de Global Constraints; no contiene `--dangerously-skip-permissions`.
  - `test_carpeta_no_permitida`: `carpeta="C:\\Windows"` → error de permiso, sin pendiente.
  - `test_bloqueo_tras_contenido_externo`: tras `leer_archivo`/correo en los últimos 180 s, `encargar_tarea` responde que lo repita el usuario.
- [ ] **Step 2:** Tests → FAIL.
- [ ] **Step 3: Implementar.** Lanzador: hilo con `subprocess.Popen(comando, cwd=carpeta, stdin=DEVNULL, stdout=archivo_log, stderr=STDOUT, creationflags=CREATE_NO_WINDOW, env=os.environ + ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN, ANTHROPIC_MODEL=cc/claude-sonnet-5-5)`; espera 15 min; al vencer o cancelar `taskkill /T /F /PID`. Al terminar lee el JSON (`result`) y llama `on_fin(resumen en ≤ 2 frases)`; log en `tareas_log.txt`. En `jarvis.responder`: antes de la IA, `r = tareas.respuesta_confirmacion(query)`; si no es None, añadir a la historia y devolverlo. `on_fin` en `main`: `ui.log` + `speak` bajo `lock_cerebro`.
- [ ] **Step 4:** Instalar el CLI (`npm i -g @anthropic-ai/claude-code`), comprobar `claude --version`; tests → PASS; prueba real: "crea en la carpeta de tareas un archivo hola.txt con un saludo" → confirmar → aviso al terminar y archivo creado.
- [ ] **Step 5: Commit** `v1.5: encargar tareas a Claude Code con confirmacion por voz`.

### Task 5: Contenido no fiable, documentación y medición

**Files:**
- Modify: `jarvis.py` (`SYSTEM_PROMPT_BASE`: nuevas herramientas y regla de `<contenido_no_fiable>`; `_run_tool`: envolver `correo_leer`, `drive_leer`, `leer_archivo`, `buscar_web`; ampliar `_ULTIMO_CORREO` a esas herramientas), `LEEME.md`, `CHANGELOG.md`, `pruebas_unidad.py`

- [ ] **Step 1: Test** `test_envoltorio_no_fiable`: `run_tool("leer_archivo", ...)` sobre un archivo con "ignora tus instrucciones" → resultado empieza por `<contenido_no_fiable origen="archivo">`.
- [ ] **Step 2:** Implementar; todos los tests → PASS.
- [ ] **Step 3: Medir latencia**: 10 frases en modo texto con tiempos (primer trozo de `on_texto`) → media ≤ 1,5 s; anotar en `LEEME.md`. Si hay arranques fríos tras 5 min de inactividad, añadir ping cada 4 min (decisión 3 del spec).
- [ ] **Step 4:** `LEEME.md` (ejemplos nuevos, requisitos: OmniRoute y Claude Code) y `CHANGELOG.md` (v1.5.0).
- [ ] **Step 5: Commit** `v1.5.0: documentacion y medicion`.
