# Jarvis v1.6 — WhatsApp (API de Meta): plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hablar con Jarvis por WhatsApp desde el móvil y que Jarvis avise por WhatsApp (fin de tareas, citas, a petición y problemas), con la WhatsApp Cloud API de Meta y ngrok.

**Architecture:** Dos módulos nuevos.
- `whatsapp.py` hace el transporte: configuración, envío con ventana de 24 h y plantilla, receptor HTTP con firma, ngrok, recordatorios y avisos de citas. Sigue el patrón `HERRAMIENTAS` + `ejecutar()`.
- `whatsapp_canal.py` hace la conversación: herramientas filtradas y la confirmación de lo delicado decidida por el código.

`jarvis.py` solo los conecta: una segunda `llm.IA` con historial propio, el mismo `lock_cerebro`, los hilos y `aviso_grave`. El HTTP se hace con la biblioteca estándar (`http.server`, `hmac`), sin dependencias nuevas.

**Tech Stack:** Python 3 (venv del proyecto), requests, `http.server.ThreadingHTTPServer`, `hmac`/`hashlib`, `unittest` (no hay pytest), WhatsApp Cloud API (Graph API), ngrok.

**Spec:** `docs/superpowers/specs/2026-10-16-jarvis-whatsapp-design.md`

## Global Constraints
- Variables en `.env`: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_MI_NUMERO` (con prefijo, sin `+` ni espacios), `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` y `NGROK_DOMINIO`.
- Variables en `ajustes.env`: `WHATSAPP_PUERTO=8766`, `WHATSAPP_AVISO_MIN=15`, `WHATSAPP_PLANTILLA=aviso_jarvis` y `WHATSAPP_API_VERSION`.
- Sin token, phone id o mi número, WhatsApp queda desactivado sin errores. Sin `WHATSAPP_APP_SECRET`, el receptor no arranca.
- Receptor solo en `127.0.0.1`, ruta `/whatsapp`.
- Plantilla `aviso_jarvis`: idioma `es` y cuerpo `Jarvis: {{1}}`.
- Ventana de servicio: 24 h desde tu último mensaje. Texto de más de 4096 caracteres → varios mensajes. `**x**` → `*x*`.
- Mensajes repetidos: se recuerdan los últimos 200 ids. Envíos recordados para el reintento: los últimos 50. Máximo 20 mensajes recibidos por minuto.
- Confirmación desde WhatsApp: caduca a los 5 min y solo puede haber una. Palabras: `tareas._SI` y `tareas._NO` sobre `pc._norm(texto)`.
- `aviso_grave`: como máximo uno cada 30 min. Recordatorios atrasados: se envían si llevan menos de 12 h, con «(con retraso)». Citas avisadas: se limpian a las 24 h.
- Archivos `whatsapp_estado.json` y `whatsapp_recordatorios.json` en la raíz del proyecto y en `.gitignore`.
- El registro nunca guarda el texto de los mensajes ni números ajenos. Comentarios del código en español sin tildes; textos para el usuario en español, cortos.
- Pruebas: `venv\Scripts\python.exe -m unittest pruebas_unidad -v` (sin red: el envío HTTP se sustituye en los tests).

## Review Focus
1. **Texto de la plantilla con saltos de línea, tabuladores o más de 4 espacios seguidos.** Meta rechaza esos parámetros, y los avisos de la IA los traen a menudo. Esperado: se sustituyen por « · » o un espacio, y se recorta a 1000 caracteres. Test en la Tarea 1.
2. **Número escrito con `+`, espacios o guiones en `.env`** (`+34 600 11 12 22`). Esperado: se normaliza a solo dígitos y se acepta igual. Test en la Tarea 1.
3. **Webhook con varios mensajes o varias entradas en un mismo POST, o sin `messages`** (solo `statuses`). Esperado: se procesan todos sin excepción. Test en la Tarea 2.
4. **«Sí, mándalo» o «Jarvis, sí.» como confirmación desde el móvil.** Esperado: confirma igual que «sí». Test en la Tarea 5.
5. **Recordatorio con `cuando` sin hora o mal formado** («mañana», «18h»). Esperado: un mensaje claro a la IA para que lo repita en ISO, sin excepción ni recordatorio guardado. Test en la Tarea 3.

---

### Task 1: Envío por WhatsApp (`whatsapp.py`, parte 1)

**Files:**
- Create: `whatsapp.py`
- Modify: `pruebas_unidad.py` (nueva clase `WhatsAppEnvio`), `.gitignore` (dos json), `.env.example` y `ajustes.env` (variables de WhatsApp, comentadas)

**Interfaces:**
- Produces:
  - `configurado() -> bool`: True si están token, phone id y mi número.
  - `mi_numero() -> str`: solo dígitos.
  - `enviar(texto: str) -> bool`
  - `marcar_recibido(momento: float | None = None) -> None`
  - `en_ventana(ahora: float | None = None) -> bool`
  - `reenviar_con_plantilla(id_mensaje: str) -> bool`
  - `para_whatsapp(texto: str) -> list[str]`: convierte el formato y lo parte.
  - `texto_plantilla(texto: str) -> str`
  - Variables de módulo para tests: `_post` (función `(url, json, headers) -> dict` con la respuesta JSON; por defecto `requests.post(..., timeout=15)`; si la respuesta trae `error`, lanza `RuntimeError(mensaje)`), `ESTADO` (`Path` de `whatsapp_estado.json`) y `_enviados` (`OrderedDict` id → texto, máximo 50).
  - El estado json es `{"ultimo_recibido": float, "citas_avisadas": {clave: momento}}`. Se lee y se escribe con `_leer_estado()` y `_guardar_estado(d)`.
- La configuración se lee con `os.getenv` en cada llamada, no al importar, para que los tests puedan cambiarla.

- [ ] **Step 1: Write the failing tests** (`class WhatsAppEnvio`; en `setUp`, variables de entorno de prueba, `ESTADO` en una carpeta temporal y `_post` falso que guarda las llamadas y devuelve `{"messages": [{"id": "wamid.N"}]}`)
  - `test_dentro_de_ventana_texto_libre`: `marcar_recibido(time.time() - 3600)`; `enviar("hola")` → True y una llamada con `json["type"] == "text"`, `json["to"] == "34600111222"`, la URL termina en `/PHONEID/messages` y la cabecera `Authorization == "Bearer TOKEN"`.
  - `test_fuera_de_ventana_plantilla`: `marcar_recibido(time.time() - 25*3600)` → `json["type"] == "template"`, `json["template"]["name"] == "aviso_jarvis"`, `["language"]["code"] == "es"` y el parámetro de texto es `"hola"`.
  - `test_sin_mensaje_previo_plantilla`: sin estado → plantilla.
  - `test_ventana_sobrevive_reinicio`: `marcar_recibido()` y después se vacía la caché en memoria (`whatsapp._cache_estado = None`) → `en_ventana()` True.
  - `test_texto_largo_partido`: 9000 caracteres → 3 envíos, cada uno ≤ 4096.
  - `test_negrita`: `para_whatsapp("**hola**")` → `["*hola*"]`.
  - `test_plantilla_limpia`: `texto_plantilla("a\nb\tc     d")` no contiene `\n`, `\t` ni 5 espacios seguidos; `len(texto_plantilla("x"*3000)) <= 1000`.
  - `test_numero_normalizado`: `WHATSAPP_MI_NUMERO="+34 600-11 12 22"` → `mi_numero() == "34600111222"`.
  - `test_reenvio_plantilla`: dentro de ventana, `enviar("hola")` guarda `wamid.1`; `reenviar_con_plantilla("wamid.1")` → True y la última llamada es una plantilla con `"hola"`; un id desconocido → False.
  - `test_error_meta_no_lanza`: `_post` lanza `RuntimeError` → `enviar` devuelve False y queda una línea `[whatsapp]` en el registro (se usa `registro.ARCHIVO` en temporal).
  - `test_sin_configurar`: sin `WHATSAPP_TOKEN` → `configurado()` False, `enviar("x")` False y ninguna llamada.

- [ ] **Step 2: Run:** `venv\Scripts\python.exe -m unittest pruebas_unidad.WhatsAppEnvio -v`. **Expected:** FAIL, `ModuleNotFoundError: whatsapp`.

- [ ] **Step 3: Implement** in `whatsapp.py`. URL: `https://graph.facebook.com/{WHATSAPP_API_VERSION}/{PHONE_ID}/messages`. Consulta la versión vigente en el changelog de la Graph API al implementar y ponla como valor por defecto de la constante `API_VERSION_DEFECTO`. El cuerpo de texto es `{"messaging_product": "whatsapp", "to": mi_numero(), "type": "text", "text": {"body": trozo}}`. El de plantilla:

```python
{"messaging_product": "whatsapp", "to": mi_numero(), "type": "template",
 "template": {"name": PLANTILLA, "language": {"code": "es"},
              "components": [{"type": "body", "parameters": [{"type": "text", "text": texto_plantilla(t)}]}]}}
```

  Los errores se anotan con `registro.error("whatsapp", "<tipo de fallo sin el texto>", "sigo sin WhatsApp")`. El estado se protege con un `threading.Lock`.

- [ ] **Step 4: Run** the same command. **Expected:** PASS. Run then the whole suite. **Expected:** OK.

- [ ] **Step 5: Commit:** `git add whatsapp.py pruebas_unidad.py .gitignore .env.example ajustes.env` y `git commit -m "v1.6: enviar por WhatsApp con ventana de 24 h y plantilla"`.

---

### Task 2: Receptor del webhook (`whatsapp.py`, parte 2)

**Files:**
- Modify: `whatsapp.py`, `pruebas_unidad.py` (nueva clase `WhatsAppReceptor`)

**Interfaces:**
- Consumes: `mi_numero()`, `marcar_recibido()` y `reenviar_con_plantilla()` (Tarea 1).
- Produces:
  - `al_recibir: Callable[[str], None] | None`, variable de módulo que asigna `jarvis.py`.
  - `procesar_peticion(metodo: str, ruta: str, cabeceras: dict, cuerpo: bytes) -> tuple[int, bytes]`: lógica pura, sin hilos. Los textos aceptados se ponen en una cola y `_despachar()` los entrega a `al_recibir` en un hilo aparte.
  - `firma_valida(cuerpo: bytes, cabecera: str) -> bool`
  - `iniciar_receptor() -> bool`: arranca `ThreadingHTTPServer(("127.0.0.1", PUERTO))` en un hilo daemon; devuelve False si falta config o secreto, o si el puerto está ocupado.
  - `parar_receptor() -> None`
  - Mensajes no de texto → `enviar("Por ahora solo leo texto.")`.

- [ ] **Step 1: Write the failing tests** (`class WhatsAppReceptor`; `al_recibir` guarda en una lista; `_despachar` se llama directamente para no depender de hilos; `_post` falso)
  - `test_verificacion_ok`: `GET /whatsapp?hub.mode=subscribe&hub.verify_token=VT&hub.challenge=123` → `(200, b"123")`.
  - `test_verificacion_mala`: token distinto → `(403, ...)`.
  - `test_firma_valida_entrega`: cuerpo con un mensaje de texto de `34600111222`, cabecera `X-Hub-Signature-256: sha256=<hmac correcto>` → 200 y `al_recibir` recibe `"hola"`; además `en_ventana()` pasa a True.
  - `test_firma_mala_403`: firma alterada o ausente → 403 y nada entregado.
  - `test_otro_numero_ignorado`: remitente `34999999999` → 200, nada entregado y en el registro no aparecen ni el número ni el texto.
  - `test_repetido_una_vez`: el mismo POST dos veces → una sola entrega.
  - `test_limite_por_minuto`: 25 mensajes distintos → 20 entregas.
  - `test_varios_mensajes_y_solo_estados`: un POST con 2 entradas y 3 mensajes → 3 entregas; un POST solo con `statuses: delivered` → 200 y nada entregado.
  - `test_fallo_131047_reenvia_plantilla`: dentro de ventana `enviar("hola")` (id `wamid.1`); POST con `statuses: [{"id": "wamid.1", "status": "failed", "errors": [{"code": 131047}]}]` → la última llamada a `_post` es una plantilla con `"hola"`.
  - `test_no_texto`: mensaje `type: "audio"` → nada entregado y un envío con «Por ahora solo leo texto.».
  - `test_servidor_real`: con `WHATSAPP_PUERTO` libre, `iniciar_receptor()` y `requests.get("http://127.0.0.1:<p>/whatsapp?...")` → 200 y el challenge; luego `parar_receptor()`. Sin `WHATSAPP_APP_SECRET` → `iniciar_receptor()` False.

- [ ] **Step 2: Run:** `venv\Scripts\python.exe -m unittest pruebas_unidad.WhatsAppReceptor -v`. **Expected:** FAIL, `AttributeError: procesar_peticion`.

- [ ] **Step 3: Implement.**
  - Firma: `hmac.compare_digest("sha256=" + hmac.new(secreto, cuerpo, hashlib.sha256).hexdigest(), cabecera)`. Las cabeceras se buscan sin distinguir mayúsculas.
  - Estructura de Meta: `entry[].changes[].value.messages[]` (`from`, `id`, `type`, `text.body`) y `value.statuses[]`.
  - Límite por minuto: un `deque` de momentos.
  - El `BaseHTTPRequestHandler` lee `Content-Length`, llama a `procesar_peticion` y no escribe nada en la consola (`log_message` vacío).

- [ ] **Step 4: Run** the same command and then the whole suite. **Expected:** PASS / OK.

- [ ] **Step 5: Commit:** `git commit -am "v1.6: receptor de WhatsApp con firma de Meta y solo tu numero"`.

---

### Task 3: Herramientas `whatsapp_enviar` y `whatsapp_recordar` (`whatsapp.py`, parte 3)

**Files:**
- Modify: `whatsapp.py`, `pruebas_unidad.py` (nueva clase `WhatsAppRecordatorios`)

**Interfaces:**
- Consumes: `enviar()` (Tarea 1).
- Produces:
  - `HERRAMIENTAS` (formato Anthropic, `input_schema`):
    - `whatsapp_enviar(texto)`: «Envía un mensaje de WhatsApp al usuario (solo a él)».
    - `whatsapp_recordar(texto, cuando)`: `cuando` en ISO local `YYYY-MM-DDTHH:MM`.
  - `ejecutar(nombre: str, args: dict) -> str | None`
  - `revisar_recordatorios(ahora: datetime | None = None) -> int`: devuelve cuántos se han enviado.
  - `RECORDATORIOS` (`Path` de `whatsapp_recordatorios.json`, lista de `{"texto", "cuando"}`).
- Textos de vuelta para la IA:
  - Enviado: «Enviado a tu WhatsApp.».
  - Sin configurar: «WhatsApp no está configurado (mira LEEME.md).».
  - Recordatorio: «Te lo recordaré por WhatsApp el <día> a las <HH:MM>.».
  - `cuando` mal formado: «No entiendo la fecha; pásala como 2026-10-17T18:00.».
  - Fecha pasada: «Esa hora ya ha pasado.».

- [ ] **Step 1: Write the failing tests**
  - `test_enviar_herramienta`: `ejecutar("whatsapp_enviar", {"texto": "x"})` → «Enviado a tu WhatsApp.» y un envío.
  - `test_enviar_no_acepta_destinatario`: el esquema de `whatsapp_enviar` solo tiene la propiedad `texto`; `ejecutar(..., {"texto": "x", "to": "34999"})` envía a `mi_numero()`.
  - `test_recordar_guarda_y_envia_a_su_hora`: `whatsapp_recordar` para dentro de 2 min → guardado en el json. `revisar_recordatorios(ahora+1min)` → 0. `revisar_recordatorios(ahora+3min)` → 1, se envía el texto y el json queda vacío.
  - `test_recordar_atrasado_tras_reinicio`: el json tiene uno de hace 2 h → se envía con «(con retraso)»; uno de hace 13 h → se descarta sin enviar.
  - `test_cuando_mal_formado`: `"mañana"`, `"18h"` y `""` → el texto «No entiendo la fecha…» y nada guardado.
  - `test_cuando_pasado`: una hora de ayer → «Esa hora ya ha pasado.».
  - `test_ajena_devuelve_none`: `ejecutar("guardar_nota", {})` → None.

- [ ] **Step 2: Run:** `... -m unittest pruebas_unidad.WhatsAppRecordatorios -v`. **Expected:** FAIL.

- [ ] **Step 3: Implement.** Usa `datetime.fromisoformat` y acepta también segundos. El json se escribe atómicamente: archivo `.tmp` y luego `replace`.

- [ ] **Step 4: Run** the same command and the whole suite. **Expected:** PASS / OK.

- [ ] **Step 5: Commit:** `git commit -am "v1.6: mandar al movil y recordatorios por WhatsApp"`.

---

### Task 4: Avisos de citas (`google_conector.py` + `whatsapp.py`)

**Files:**
- Modify: `google_conector.py` (nueva función), `whatsapp.py`, `pruebas_unidad.py` (nueva clase `WhatsAppCitas`)

**Interfaces:**
- Produces:
  - `google_conector.eventos_proximos(minutos: int) -> list[dict]`: `[{"id": str, "titulo": str, "inicio": datetime}]`, eventos que empiezan entre ahora y ahora+minutos. Excluye los de día completo y reutiliza `_servicio("calendar")` y `_fecha_evento`.
  - `whatsapp.revisar_citas(eventos: list[dict], ahora: float | None = None) -> int`: avisa «En 15 min: <titulo> (<HH:MM>)», con los minutos reales redondeados. Clave anti-repetición: `f"{id}|{inicio.isoformat()}"` en `citas_avisadas`; limpia las de más de 24 h.

- [ ] **Step 1: Write the failing tests**
  - `test_eventos_proximos_sin_dia_completo`: servicio falso en `google_conector._pruebas["calendar"]` con un evento a las +10 min y uno de día completo → solo el primero, con `inicio` como datetime.
  - `test_cita_avisada_una_vez`: `revisar_citas([ev])` dos veces → 1 envío, y el texto contiene el título y la hora.
  - `test_no_repite_tras_reinicio`: tras avisar, `_cache_estado = None` → `revisar_citas([ev])` da 0.
  - `test_cita_movida_avisa_de_nuevo`: mismo id con otro `inicio` → avisa.
  - `test_limpia_antiguas`: una clave avisada hace 25 h desaparece del estado.

- [ ] **Step 2: Run:** `... -m unittest pruebas_unidad.WhatsAppCitas -v`. **Expected:** FAIL.

- [ ] **Step 3: Implement** both functions.

- [ ] **Step 4: Run** the same command and the whole suite. **Expected:** PASS / OK.

- [ ] **Step 5: Commit:** `git commit -am "v1.6: aviso de citas por WhatsApp"`.

---

### Task 5: Conversación desde el móvil (`whatsapp_canal.py`)

**Files:**
- Create: `whatsapp_canal.py`
- Modify: `pruebas_unidad.py` (nueva clase `WhatsAppCanal`)

**Interfaces:**
- Consumes: `tareas.respuesta_confirmacion`, `tareas._SI`, `tareas._NO` y `pc._norm`.
- Produces:
  - `PERMITIDAS: set[str]`, exactamente las de la especificación: `guardar_nota`, `anadir_al_diario`, `buscar_en_cerebro`, `leer_nota`, `notas_recientes`, `procesar_bandeja`, `calendario_eventos`, `correo_buscar`, `correo_leer`, `correo_borrador`, `drive_buscar`, `drive_leer`, `buscar_web`, `buscar_archivos`, `leer_archivo`, `listar_carpeta`, `hora_actual`, `whatsapp_recordar`, `estado_tarea` y `cancelar_tarea`.
  - `CON_CONFIRMACION = {"correo_enviar", "calendario_crear", "drive_crear_documento", "encargar_tarea"}`
  - `filtrar(tools: list[dict]) -> list[dict]`: deja las de `PERMITIDAS | CON_CONFIRMACION`.
  - `class Canal`, con:
    - `__init__(self, run_tool: Callable[[str, dict], str])`
    - `run_tool(self, nombre: str, args: dict) -> str`: para la IA. Rechaza las no filtradas con «Esa herramienta no está disponible por WhatsApp.». Intercepta las tres de confirmación propia y deja pasar `encargar_tarea` al `run_tool` original, que ya pide su confirmación.
    - `antes_de_la_ia(self, texto: str) -> str | None`: decide la confirmación o devuelve None.
    - `pendiente(self) -> dict | None`: con caducidad de 5 min.
  - `PROMPT_EXTRA = "Hablas por WhatsApp: respuestas breves, sin abrir programas ni webs; el usuario no está delante del PC."`
- Texto que recibe la IA al interceptar: «Pendiente de confirmación: resume al usuario exactamente lo que se va a hacer (<herramienta> con <args>) y pídele que conteste sí.».

- [ ] **Step 1: Write the failing tests**
  - `test_filtrar`: de una lista con `abrir_programa`, `abrir_carpeta`, `abrir_web`, `whatsapp_enviar`, `guardar_nota` y `correo_enviar` quedan solo `guardar_nota` y `correo_enviar`.
  - `test_no_permitida_rechazada`: `canal.run_tool("abrir_programa", {...})` → el texto de no disponible, y el original no se llama.
  - `test_correo_se_intercepta`: `run_tool("correo_enviar", args)` no llama al original y devuelve el texto «Pendiente de confirmación…».
  - `test_si_ejecuta`: después, `antes_de_la_ia("Sí, mándalo")` → llama al original con los mismos args y devuelve su resultado. `antes_de_la_ia("Jarvis, sí.")` también vale.
  - `test_no_cancela`: `antes_de_la_ia("no")` → «Vale, no lo hago.» y el original no se llama.
  - `test_otra_cosa_cancela_y_sigue`: `antes_de_la_ia("¿qué tengo mañana?")` → None y `pendiente()` None.
  - `test_caduca`: pendiente creado hace 6 min (se ajusta `momento`) → `antes_de_la_ia("sí")` da None y no se ejecuta.
  - `test_encargar_tarea_usa_tareas`: `run_tool("encargar_tarea", ...)` llama al original; con `tareas._pendiente` puesto, `antes_de_la_ia("sí")` devuelve lo que diga `tareas.respuesta_confirmacion` (se sustituye `tareas._lanzar` y `tareas.ejecutable` para no lanzar nada).

- [ ] **Step 2: Run:** `... -m unittest pruebas_unidad.WhatsAppCanal -v`. **Expected:** FAIL.

- [ ] **Step 3: Implement.** Normaliza con `pc._norm`, quita la palabra de activación como hace `tareas.respuesta_confirmacion` y aplica `_SI` y `_NO`. Primero mira `tareas.respuesta_confirmacion(texto)`; si devuelve algo, eso es la respuesta.

- [ ] **Step 4: Run** the same command and the whole suite. **Expected:** PASS / OK.

- [ ] **Step 5: Commit:** `git commit -am "v1.6: conversacion por WhatsApp con confirmacion de lo delicado"`.

---

### Task 6: ngrok (`whatsapp.py`, parte 4)

**Files:**
- Modify: `whatsapp.py`, `pruebas_unidad.py` (nueva clase `WhatsAppNgrok`)

**Interfaces:**
- Produces:
  - `buscar_ngrok() -> str | None`: busca en el PATH, en `%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe`, en `%LOCALAPPDATA%\ngrok\ngrok.exe` y en `%USERPROFILE%\ngrok\ngrok.exe`.
  - `comando_ngrok(exe: str) -> list[str]`: `[exe, "http", f"--url=https://{NGROK_DOMINIO}", str(PUERTO), "--log=stdout"]`.
  - `ngrok_ya_publica() -> bool`: `GET http://127.0.0.1:4040/api/tunnels` con 1 s de espera; True si algún `public_url` contiene el dominio.
  - `iniciar_ngrok() -> str | None`: None si todo va bien o no hay dominio configurado; si no, el texto del problema para `aviso`. Usa `Popen` con `CREATE_NO_WINDOW`, salida a `ngrok_log.txt`, y comprueba a los 3 s que sigue vivo.
  - `parar_ngrok() -> None`: `taskkill /T /F` como `tareas._matar`.

- [ ] **Step 1: Write the failing tests**
  - `test_comando`: con `NGROK_DOMINIO=abc.ngrok-free.app` y `WHATSAPP_PUERTO=8766` → la lista exacta de arriba.
  - `test_sin_dominio_no_lanza`: `iniciar_ngrok()` → None y no se llama a `Popen` (que se sustituye).
  - `test_sin_exe`: dominio puesto y `buscar_ngrok` → None. Resultado: el texto contiene «ngrok» y «LEEME».
  - `test_ya_publicado_no_lanza`: `ngrok_ya_publica` → True; no se llama a `Popen`.

- [ ] **Step 2: Run:** `... -m unittest pruebas_unidad.WhatsAppNgrok -v`. **Expected:** FAIL.

- [ ] **Step 3: Implement.** `ngrok_log.txt` ya queda cubierto por `*_log.txt` en `.gitignore`.

- [ ] **Step 4: Run** the same command and the whole suite. **Expected:** PASS / OK.

- [ ] **Step 5: Commit:** `git commit -am "v1.6: Jarvis arranca y cierra ngrok"`.

---

### Task 7: Conectar todo en `jarvis.py`

**Files:**
- Modify: `jarvis.py`:
  - `TOOLS` (+`whatsapp.HERRAMIENTAS`)
  - `_run_tool` (despacho a `whatsapp.ejecutar`)
  - prompt de sistema: línea «WHATSAPP: whatsapp_enviar si te pide mandarle algo al móvil; whatsapp_recordar para recordatorios por WhatsApp (convierte la hora a ISO con la fecha actual).»
  - `aviso` de micrófono mudo (línea ~308), `responder`, `vigilante_google`, `main`
- Modify: `pruebas_unidad.py` (nueva clase `WhatsAppJarvis`)

**Interfaces:**
- Consumes: Tareas 1–6.
- Produces:
  - `aviso_grave(texto: str) -> None`: llama a `aviso(texto)` y además a `whatsapp.enviar("⚠️ " + texto)` si han pasado 30 min desde el último. Usa la variable de módulo `_ultimo_grave`.
  - `crear_ia_whatsapp(canal: whatsapp_canal.Canal) -> llm.IA`: como `crear_ia`, pero con `whatsapp_canal.filtrar(TOOLS)`, `canal.run_tool` y `lambda: system_prompt() + "\n" + whatsapp_canal.PROMPT_EXTRA`.
  - `atender_whatsapp(texto: str) -> None`: con `lock_cerebro`:
    1. `ui.log("tu", "[WhatsApp] " + texto)`.
    2. `canal.antes_de_la_ia(texto)`.
    3. Si devuelve None, añade el mensaje al historial `history_wa` (recortado a 24) y llama a `ia_wa.responder`. Si es `llm.IAError`, contesta «Ahora mismo no puedo pensar; inténtalo en un rato.», lo anota y llama a `aviso_grave`.
    4. `whatsapp.enviar(respuesta)`.
    5. `ui.log("jarvis", "[WhatsApp] " + respuesta)`.
- En `responder` (voz), en la rama `except llm.IAError` (`llm.IA.responder` solo la lanza cuando han fallado todos los proveedores de la lista), llama además a `aviso_grave("No puedo conectar con ninguna IA.")`.
- En `vigilante_google`, al perder el permiso: `aviso_grave("He perdido el acceso a Google; ejecuta conectar_google.bat.")`. El `speak` se mantiene.
- Micrófono mudo: `aviso_grave` en lugar de `aviso`.
- En `main`, solo en modo ventana y solo si `whatsapp.configurado()`:
  1. Crea `canal`, `ia_wa` y `history_wa`, y asigna `whatsapp.al_recibir = atender_whatsapp`.
  2. Llama a `whatsapp.iniciar_receptor()`. Si da False, `aviso("WhatsApp: falta WHATSAPP_APP_SECRET o el puerto está ocupado; solo envío avisos.")`.
  3. Llama a `whatsapp.iniciar_ngrok()`. Si devuelve un texto, lo pasa a `aviso` y lo dice una vez con `speak` (dentro de `lock_cerebro`).
  4. `tareas.on_fin` envuelve el actual y llama además a `whatsapp.enviar(texto)`.
  5. Arranca un hilo `vigilante_whatsapp`. Cada 30 s llama a `whatsapp.revisar_recordatorios()`. Cada 60 s, si `google_conector.estado()` está conectado, llama a `whatsapp.revisar_citas(google_conector.eventos_proximos(AVISO_MIN))`. Cualquier excepción se anota y el bucle sigue.
  6. Antes de `os._exit(0)`: `whatsapp.parar_ngrok()` y `whatsapp.parar_receptor()`.

- [ ] **Step 1: Write the failing tests** (`class WhatsAppJarvis`; importa `jarvis`; `whatsapp._post` falso; `jarvis.ia_wa` con un `llm.IA` cuyo `responder` se sustituye)
  - `test_herramientas_en_tools`: `whatsapp_enviar` y `whatsapp_recordar` están en `jarvis.TOOLS`, y `jarvis.run_tool("whatsapp_enviar", {"texto": "x"})` envía.
  - `test_ia_whatsapp_filtrada`: los nombres de `crear_ia_whatsapp(canal).tools` no incluyen `abrir_programa` y sí `guardar_nota`.
  - `test_atender_whatsapp_responde_por_whatsapp`: la IA falsa devuelve «Hecho.» → un envío con «Hecho.», y `history_wa` tiene el mensaje del usuario y la respuesta; el historial de voz no cambia.
  - `test_atender_whatsapp_ia_caida`: la IA lanza `llm.IAError` → se envía «Ahora mismo no puedo pensar; inténtalo en un rato.».
  - `test_aviso_grave_limitado`: dos `aviso_grave` seguidos → un solo envío. Con `_ultimo_grave` 31 min atrás → otro envío.

- [ ] **Step 2: Run:** `... -m unittest pruebas_unidad.WhatsAppJarvis -v`. **Expected:** FAIL.

- [ ] **Step 3: Implement** as above.

- [ ] **Step 4: Run** the same command and the whole suite. **Expected:** PASS / OK. Además, arranca `jarvis.py --texto` sin variables de WhatsApp en `.env`, escribe «hola» y luego «salir». **Expected:** responde igual que antes, sin errores de WhatsApp.

- [ ] **Step 5: Commit:** `git commit -am "v1.6: Jarvis habla y avisa por WhatsApp"`.

---

### Task 8: Diagnóstico y guía para el usuario

**Files:**
- Modify: `diagnostico.py` (nueva sección `9. WHATSAPP` antes de `FIN`), `LEEME.md` (sección «WhatsApp, paso a paso»), `README.md` (variables y fila de `whatsapp.py`/`whatsapp_canal.py` en la tabla), `CHANGELOG.md` (entrada v1.6)

**Interfaces:**
- Consumes: `whatsapp.configurado`, `buscar_ngrok` y `ngrok_ya_publica`.
- La sección de diagnóstico comprueba, sin mostrar claves:
  - qué variables faltan;
  - `GET https://graph.facebook.com/<ver>/<PHONE_ID>?fields=display_phone_number,verified_name` con el token → OK o el error;
  - `GET .../<WABA>/message_templates?name=<PLANTILLA>` solo si se configura `WHATSAPP_WABA_ID`; si no, lo indica como opcional;
  - si `ngrok.exe` existe;
  - si el dominio responde a `GET https://<dominio>/whatsapp?hub.mode=x` con algo distinto de un error de conexión.
- La guía de `LEEME.md` sigue los 6 pasos de la especificación («Lo que tiene que hacer el usuario»), con los nombres exactos de los botones de Meta y ngrok comprobados al escribirla. Termina con «Comprueba con diagnostico.bat».

- [ ] **Step 1: Run** `diagnostico.bat` without WhatsApp configured. **Expected:** la sección 9 dice qué falta y el diagnóstico termina en `FIN` sin trazas de error.
- [ ] **Step 2: Write** las secciones de documentación.
- [ ] **Step 3: Commit:** `git commit -am "v1.6: diagnostico y guia de WhatsApp"`.

---

### Task 9: Prueba real con Meta (con el usuario)

Depende de que el usuario haya hecho los pasos de la guía. Esto no se automatiza.

- [ ] **Step 1:** El usuario rellena `.env` y ejecuta `diagnostico.bat`. **Expected:** la sección 9 está toda en OK.
- [ ] **Step 2:** Arranca Jarvis desde el acceso directo y registra el webhook en Meta. **Expected:** Meta marca la verificación como correcta.
- [ ] **Step 3:** Escribe «hola» desde el móvil. **Expected:** respuesta en ≤ 10 s y `[WhatsApp]` en la ventana.
- [ ] **Step 4:** «Envíame un correo de prueba a mí mismo» y luego «sí». **Expected:** primero pide confirmación y, tras el «sí», el correo llega.
- [ ] **Step 5:** Por voz, «Jarvis, recuérdame por WhatsApp dentro de 2 minutos beber agua». **Expected:** llega el mensaje a la hora.
- [ ] **Step 6:** Comprueba la plantilla. **Expected:** aprobada y enviable desde el número de prueba (`hello_world` y `aviso_jarvis`). Si Meta no deja plantillas propias con el número de prueba, se documenta en `LEEME.md` y en `CHANGELOG.md` como limitación, como dice la especificación.
- [ ] **Step 7:** Anota los resultados en `CHANGELOG.md` y haz commit.
