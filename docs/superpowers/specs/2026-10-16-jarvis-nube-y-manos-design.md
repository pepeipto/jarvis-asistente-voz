# Jarvis v1.5 — Cerebro en la nube (OmniRoute) y manos en el PC

Fecha: 2026-10-16 · Estado: borrador revisado (Claude + Gemini 3.8 Flash vía OmniRoute), pendiente de aprobar

## Objetivo
Que Jarvis haga las tareas que el usuario le mande ("programas o lo que sea"), con respuestas de voz
rápidas, usando la nube a través de OmniRoute en lugar de qwen local.

Criterios de éxito:
- Respuesta de voz: primera palabra en ≤ 1,5 s de media (igual o mejor que hoy con qwen).
- Puede abrir cualquier programa instalado, abrir carpetas, buscar y leer archivos del PC.
- Puede encargar tareas complejas (organizar archivos, programar, informes) y avisar al terminar.
- Ninguna acción destructiva sin confirmación explícita del usuario.

## Decisiones
1. **Cerebro principal: `cc/claude-haiku-5-5` vía OmniRoute** (medido: 0,75 s al primer token en caliente).
   Configurable con `CLAUDE_MODEL`. `LLM_PROVEEDOR=auto` pasa a significar: nube primero; si falla o
   tarda > 4 s, `auto/best-free` vía OmniRoute; si tampoco hay red, Ollama con un modelo pequeño
   (`OLLAMA_MODEL_RESPALDO`, por defecto `granite4.1:8b`, carga en pocos segundos) en lugar de qwen 27B.
   Ollama deja de arrancarse al inicio.
2. **Streaming en Anthropic**: `_anthropic` usa `messages.stream` y llama a `on_texto` por trozos; el
   troceo en frases que ya existe para Ollama se reutiliza tal cual.
3. **Calentamiento**: un único cliente reutilizado (conexión persistente) y una petición mínima
   (max_tokens=1) solo al arrancar. Si la medición muestra arranques fríos tras inactividad, se añade
   un ping periódico; si no, no.
4. **Búsqueda web**: herramienta `buscar_web(consulta)` que obtiene los 3-5 primeros resultados
   (título, fragmento, URL) de DuckDuckGo vía OmniRoute y se los devuelve a Haiku, que redacta la
   respuesta hablada. Resultado tratado como contenido no fiable (ver Seguridad).
5. **Manos rápidas** (nuevo módulo `pc.py`, mismo patrón `HERRAMIENTAS` + `ejecutar()`):
   - `abrir_programa(nombre)`: índice en memoria de los `.lnk` del menú Inicio (usuario y común),
     creado al arrancar; las apps de la tienda (`Get-StartApps`) se añaden en un hilo en segundo plano
     una vez al arrancar. Coincidencia aproximada con `difflib`; se abre con `os.startfile`. Sustituye a
     la lista fija `APPS` (que se mantiene como alias).
   - `abrir_carpeta(ruta_o_nombre)`: abre en el Explorador; acepta alias (escritorio, documentos,
     descargas, imágenes) o ruta.
   - `buscar_archivos(texto, carpeta="", maximo=10)`: búsqueda por nombre con `os.scandir` en carpetas
     del usuario (Escritorio, Documentos, Descargas, OneDrive y unidades extra configurables en
     `ajustes.env` `CARPETAS_PERMITIDAS`), con límite de 3 s y de profundidad; omite carpetas ocultas,
     `node_modules`, `venv` y archivos de OneDrive solo en la nube (atributos OFFLINE /
     RECALL_ON_DATA_ACCESS), que tampoco se leen salvo petición expresa.
   - `leer_archivo(ruta)`: texto, PDF y Word (reutiliza pypdf/python-docx ya instalados); máx. ~8000
     caracteres, con aviso si se recorta.
   - `listar_carpeta(ruta)`: nombres, tamaños y fechas (máx. 50 entradas).
   Todo es de solo lectura o apertura; no borra, mueve ni ejecuta comandos.
6. **Manos grandes: `encargar_tarea(descripcion, carpeta="")`** (nuevo módulo `tareas.py`):
   - Lanza Claude Code en modo no interactivo (`claude -p ... --output-format json`) en segundo plano,
     con `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` de OmniRoute y modelo `cc/claude-sonnet-5-5`.
   - Permisos por **lista de permitidos**, no de prohibidos: `--allowedTools` con Read, Glob, Grep,
     Edit, Write y WebSearch; sin Bash libre (solo patrones concretos de solo lectura como `git status`).
     En modo `-p` todo lo no permitido se deniega solo. Carpeta de trabajo = la indicada (validada contra
     `CARPETAS_PERMITIDAS`), por defecto `Documentos\Jarvis\tareas`.
   - Proceso: hilo con `subprocess.Popen` (`stdin=DEVNULL`, salida a archivo de log, `CREATE_NO_WINDOW`),
     tiempo máximo 15 min, y se mata el árbol de procesos al cancelar o al vencer.
   - Jarvis responde al momento ("Me pongo con ello") y, al terminar, dice un resumen de lo hecho y lo
     escribe en la ventana. Una tarea a la vez; `estado_tarea` y `cancelar_tarea` para seguirla.
   - Requiere instalar el CLI de Claude Code (`npm i -g @anthropic-ai/claude-code`); `instalar.bat` y
     `diagnostico.py` lo comprueban.
7. **Confirmación por voz** para lo que cambia cosas: antes de `encargar_tarea`, Jarvis repite la tarea
   exacta (y la carpeta) y espera "sí"/"adelante"; la confirmación la decide el código, no la IA. Se reutiliza la ventana de 10 s de seguir hablando. Enviar correo ya existe
   y pasa a usar la misma confirmación.

## Seguridad
- Archivos leídos, páginas web y correos son datos, no órdenes: el resultado de esas herramientas se
  envuelve en `<contenido_no_fiable origen="...">` y el system prompt prohíbe seguir instrucciones de
  dentro. Además se mantiene la regla actual (180 s sin abrir enlaces tras leer correo) y se extiende a
  `leer_archivo` y `buscar_web`, también para `encargar_tarea`.
- La confirmación de `encargar_tarea` (decisión 7) es la barrera principal: nada se ejecuta sin que el
  usuario oiga la tarea exacta y diga que sí.
- Rutas: se resuelven con `Path.resolve()` (sigue enlaces, junctions, `..` y nombres 8.3) y deben quedar
  dentro de `CARPETAS_PERMITIDAS`; siempre prohibidos `C:\Windows`, `Program Files`, `.ssh`, `.env`,
  `AppData` (perfiles de navegador, gestores de claves) aunque estén dentro.
- Claude Code: lista de permitidos (decisión 6), nunca `--dangerously-skip-permissions`.
- El contenido de notas y archivos viaja a la nube solo cuando una herramienta lo lee para responder.

## Errores
- OmniRoute caído o sin internet → respaldo a Ollama con aviso hablado ("Sin conexión, uso el modo local").
- Límite de uso de la suscripción (429) → se reintenta una vez con `auto/best-free`, luego Ollama.
- CLI de Claude Code ausente → `encargar_tarea` responde cómo instalarlo; el resto sigue funcionando.
- Todo error se registra con `registro.error` como hoy.

## Pruebas
- `prueba_auto.py`: añadir casos de `pc.py` (buscar/leer/listar con carpetas temporales, rechazo de rutas
  prohibidas, `..`, enlaces simbólicos y junctions que salen fuera), de streaming (mock del cliente) y del orden nube→Ollama.
- Medir latencia con 10 frases reales antes y después; criterio ≤ 1,5 s de media.

## Fuera de alcance (siguientes versiones)
- Añadir proveedores gratuitos a OmniRoute (Groq, Cerebras, Google AI Studio…) con cuentas propias del
  usuario: se configura en OmniRoute, no en Jarvis.
- Controlar programas con clics (computer-use) y automatizar Excel/Word por dentro.
- Varias tareas en paralelo.
