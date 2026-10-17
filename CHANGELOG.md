# Registro de cambios de Jarvis

Cada versión anota qué cambió, por qué y cómo se comprobó.
Formato: **MAYOR.MENOR.PARCHE**
- MAYOR: cambia la forma de usar Jarvis.
- MENOR: funciones nuevas.
- PARCHE: arreglos.

Las mejoras propuestas esperan en **Pendiente de aprobación** (al final) hasta que digas "sí" a cada una.

---

## [1.10.0] - 17/10/2026 - Claude Code con acceso a tus carpetas
**Por qué:** pediste por voz «crea notas de todas mis conversaciones» y la tarea falló: Claude Code solo
podía tocar `Documentos\Jarvis\tareas`. Querías que Jarvis pudiera usar Claude Code él solo con lo que pidas.

- **Carpetas de trabajo:** Claude Code puede leer y escribir en tus carpetas (Escritorio, Documentos,
  Descargas, Imágenes, Música, Vídeos, OneDrive), en el **segundo cerebro** y en el **propio Jarvis** (para
  mejorarse a sí mismo en modo programador). Se puede pedir «en el cerebro» o «en Jarvis».
- **Tareas normales:** además de leer y editar, pueden mover, copiar y crear carpetas. Borrar sigue sin estar
  permitido.
- **Protegido siempre:** ningún `.env`, los permisos de Google de Jarvis, `~/.ssh` ni la configuración de
  Claude Code. Medido: la regla `**/.env` no protegía rutas fuera de la carpeta de trabajo (Claude Code leyó
  el `.env` de Jarvis en la prueba); con `//**/.env` sí queda bloqueado.
- **Sin pedir el «sí» si lo quieres:** `TAREAS_CONFIRMAR=0` en `ajustes.env` lanza las tareas de voz al
  momento. Por defecto sigue pidiéndolo. Por WhatsApp siempre lo pide, y el bloqueo de 3 min tras leer
  correos o internet se mantiene.
- **Notas en el cerebro:** `cerebro/notas/Claude/` tiene 14 notas (una por conversación, archivos, pendientes)
  y `cerebro/documentos/proyecto-jarvis/` copias del CHANGELOG, el LEEME y los diseños.

**Comprobado:** 176 pruebas automáticas; tareas reales: leyó la nota de pendientes del cerebro y escribió un
resumen, contó bien sus 7 pendientes, y un `.env` de prueba quedó bloqueado.

## [1.9.0] - 17/10/2026 - Cadena de proveedores gratuitos
**Por qué:** gastar menos y que Jarvis no se quede sin cerebro si Claude se agota.

- **Cadena gratuita:** si Claude (tu suscripción, por OmniRoute) falla o se agota, Jarvis prueba en orden
  Gemini 3 Flash y Claude Sonnet 4.6 (Antigravity), GPT-5.6 Luna (DuckDuckGo) y `auto/best-fast`, y al
  final Ollama. Se cambia con `MODELOS_GRATIS`. Elegidos midiendo 24 modelos: todos
  responden en español y usan herramientas. **`auto/best-free`, el respaldo de antes, no usaba herramientas**
  (no podía apuntar, mirar la hora o el tiempo), por eso sale de la cadena.
- **Límite de uso (429):** ese modelo descansa 1 min y se pasa al siguiente sin esperar.
- **El buscador de Claude solo se pide a Claude de Anthropic** (`cc/`, `claude/`): `antigravity/claude-...`
  no lo tiene, y si un modelo no lo admite se quita solo a ese modelo, no a todos.
- **Ya no dice que ha hecho algo que falló:** visto en la prueba real («Anotado queda en el diario» con la
  herramienta fallando). Tras un fallo, Jarvis no habla hasta tener la respuesta completa y, si afirma
  haberlo hecho, dice la verdad.
- **OmniRoute ya no se lleva tus claves de Jarvis:** se abría desde la carpeta de Jarvis y leía su `.env`
  (WhatsApp, ElevenLabs...). Ahora arranca desde `~/.omniroute` y sin esas variables.
- **«mi combo» de OmniRoute arreglado:** solo tenía un modelo y estaba roto (Codex sin configurar). Ahora:
  Claude Sonnet 4.6 y Gemini 3 Flash (gratis), Claude Sonnet 5.5 (suscripción), GPT-5.6 Luna y
  `auto/best-fast`, con tu estrategia `context-relay`. Copia del original en `~/.omniroute/copias/`.
- **Guía de proveedores gratuitos** en el LEEME (Google AI Studio, Groq, Cerebras, OpenRouter, Mistral...).

**Comprobado:** 170 pruebas automáticas; prueba real con Claude «agotado»: respondió Gemini gratis en
1,5-6 s usando hora, tiempo y diario, y ante un fallo del diario lo dijo en vez de mentir; «mi combo»
respondió en 4 s.

## [1.8.0] - 17/10/2026 - Arranque a prueba de fallos e internet de verdad
**Por qué:** «falla cada vez que lo enciendo» y «no sabe nada actual». Se reprodujo y había cinco causas.

**Arranque y cerebro:**
- **OmniRoute cerrado = Jarvis tonto.** Si OmniRoute no estaba abierto, Jarvis usaba siempre el modelo local
  pequeño (granite 8B). Ahora **Jarvis abre OmniRoute solo** al arrancar (sin ventana, ~5 s), lo vigila cada
  minuto (si se cae, lo reabre) y al salir cierra solo el que abrió él (`omniroute.py`).
- **Se quedaba callado.** Si la IA devolvía una respuesta vacía, Jarvis no decía nada (visto en tu sesión de
  las 21:03). Ahora una respuesta vacía cuenta como fallo y pasa al siguiente cerebro; si fallan todos, lo dice.
- **Sin saldo o clave mala:** ese proveedor se aparta 10 min en vez de reintentarlo (y esperar) en cada pregunta.
- **API directa de Anthropic bien detectada:** `api.anthropic.com` ya no se trata como un proxy (antes le
  mandaba el token de OmniRoute y fallaba siempre). El `.env` manda sobre variables de fuera.
- Si la nube no responde al arrancar, deja cargado el modelo local para que la primera respuesta no tarde.

**Internet (busca sin preguntar):**
- **Buscador de Claude:** el cerebro en la nube usa la búsqueda web de Anthropic (todo internet, con
  fuentes) a través de OmniRoute. Mientras busca, Jarvis dice «Déjame mirar». Medido: noticias, F1, precios y
  tiempo con datos reales en 3-5 s.
- **DuckDuckGo había puesto un reto anti-robots** y Jarvis lo tomaba por «no hay resultados». Ahora: versión
  lite → versión HTML → Wikipedia (nunca se intenta resolver un reto), y si no hay nada, lo dice y prueba otra vía.
- **Nuevas herramientas:** `leer_web` (lee una página; nunca este PC ni tu red local, ni tras redirecciones)
  y `tiempo` (Open-Meteo, gratis y sin clave: ahora y 3 días).
- **Prompt:** busca siempre que haga falta, sin pedir permiso; nunca dice «no tengo acceso a internet».
- **Ya no «confiesa» inventos que no hizo:** antes Jarvis guardaba solo el texto final y, en la siguiente
  pregunta, Claude veía citas sin búsqueda y decía haberlas inventado. Ahora se guarda la búsqueda real.
- **Seguridad:** lo que Claude lee en internet activa las mismas cautelas que `buscar_web` (3 min sin
  encargar tareas ni abrir enlaces), y todo llega marcado como contenido no fiable.

**Comprobado:** 161 pruebas automáticas (24 nuevas); arranque real de `jarvis.py` 3 de 3 sin errores
(OmniRoute abierto solo, Claude listo en 5-7 s); conversación real de 6 preguntas con internet, primera
palabra en 1-2 s, sin autocorrecciones falsas.
**Sin comprobar todavía:** una conversación hablada larga con tu voz.

## [1.7.0] - 17/10/2026 - Oído fiable y Jarvis programador
**Por qué:** a veces Jarvis no escuchaba. Se reprodujo en este PC y se encontraron tres causas.

**Oído (arreglos):**
- **Cambiaba de micrófono al azar.** El OBSBOT Tiny 2 Lite tiene supresión de ruido: en silencio da casi
  ceros (pico 1 de 32768) y Jarvis lo daba por «silenciado». En cada arranque elegía otro al azar
  (MSI Sound Tune, Realtek...), lejos de ti. Medido: 3 arranques, 3 elecciones distintas. Ahora solo es
  «mudo» un micrófono que da ceros exactos (silenciado o sin permiso). Tras el arreglo: 3 de 3, el OBSBOT.
- **Tras 3 minutos callado, se reiniciaba el oído** por la misma confusión, y podía volver a cambiar de
  micrófono. Arreglado con el mismo criterio.
- **Nunca elige solo una entrada que no es un micrófono** (líneas, «Stream Out», cables virtuales).
- **Podía quedarse sordo para siempre:** si algo fallaba mientras preparaba la respuesta, el micrófono
  quedaba silenciado sin fin. Ahora siempre vuelve a escuchar.
- **Nuevo ajuste `UMBRAL_VOZ`** (`ajustes.env`, por defecto 0.01): bájalo si no te oye cuando hablas bajo o
  lejos; súbelo si se activa con ruidos. Al arrancar, la consola muestra el umbral usado.

**Jarvis programador (nuevo):**
- **Modo programador** en `encargar_tarea` (`programar=true`): Claude Code ya no solo lee y edita; también
  ejecuta Python, pruebas (pytest/unittest), pip/uv, Node/npm, Rust, Go y .NET, y hace commits locales en una
  rama nueva. Sigue las pautas de un programador senior (leer antes, escribir y pasar pruebas, commits
  pequeños, dependencias en un entorno virtual). Límite de 40 min por tarea (15 en las normales).
  Nunca `git push`, nunca consola libre, y sigue pidiendo tu «sí».
- **Continuar la última tarea** (`continuar=true`): «Jarvis, ahora añade...» reanuda la misma sesión de Claude
  Code, en la misma carpeta y con todo su contexto (también pide «sí»).
- **Credenciales correctas para Claude Code:** con OmniRoute usa el token y los modelos `cc/...`; con la API
  directa de Anthropic usa la clave y el nombre sin `cc/` (antes le quitaba la clave y fallaba con
  «Not logged in»).
- **Errores en español:** «no tiene saldo», «no tiene sesión», «¿está OmniRoute abierto?» en vez del error
  en inglés.
- **Seguridad, a tener en cuenta:** poder ejecutar código da mucho poder. Por eso se mantiene la
  confirmación por voz y el bloqueo de 3 min tras leer correos, archivos o internet.

**Comprobado:** 137 pruebas automáticas (12 nuevas); prueba real del micrófono en este PC (elección,
calibración y 8 min de silencio simulados sin reinicio); prueba real de programación por OmniRoute: Jarvis
encargó crear `calculo.py` con pruebas (4 pasan, 14 s) y luego continuó la sesión añadiendo `resta` (7 pasan, 11 s).
**Sin comprobar todavía:** una conversación hablada larga con tu voz real.
**Para que funcione el modo programador:** OmniRoute abierto (tu `.env` apunta ahora a la API directa,
que no tiene saldo), recargar saldo de la API, o iniciar sesión en Claude Code (`claude` y luego `/login`).

## [1.6.0] - 17/10/2026 - Jarvis en WhatsApp
Diseño: `docs/superpowers/specs/2026-10-16-jarvis-whatsapp-design.md`.

- **Avisos a tu móvil:** fin de tareas, citas próximas (15 min antes), recordatorios que le pidas por voz
  (`whatsapp_recordar`), envío a petición (`whatsapp_enviar`) y problemas sin reparar (máximo uno cada 30 min).
  Dentro de las 24 h de tu último mensaje va como texto libre; fuera, dentro de la plantilla `aviso_jarvis`.
- **Conversación desde el móvil:** escribes a Jarvis por WhatsApp y contesta con texto. Lo delicado
  (enviar correos, crear citas o documentos, encargar tareas) solo se hace si tu siguiente mensaje es un «sí»,
  decidido por el código; caduca a los 5 minutos. Jarvis no abre programas ni webs desde ahí.
- **Entrada segura:** receptor solo en `127.0.0.1`, publicado por ngrok con dominio fijo (Jarvis lo arranca
  y lo cierra). Cada petición lleva la firma de Meta o se rechaza; solo se atiende tu número; sin repetidos
  y con límite por minuto. El registro nunca guarda el texto de los mensajes.
- **Diagnóstico y guía:** `diagnostico.bat` tiene la sección 9 (variables, token, plantilla, ngrok, dominio)
  y `LEEME.md` explica el alta paso a paso.
- **Límites conocidos:** solo funciona con el PC encendido y Jarvis abierto; los mensajes con Jarvis cerrado
  no se recuperan. Con el número de prueba de Meta, la plantilla propia podría requerir verificación; sin ella,
  los avisos fuera de las 24 h quedan limitados.

**Comprobado:** pruebas automáticas sin red (`pruebas_unidad.py`) y `diagnostico.bat` sin WhatsApp configurado.
**Sin comprobar todavía:** la prueba real con Meta (ida y vuelta, plantilla, confirmación, recordatorio).

## [1.5.0] - 16/10/2026 - Cerebro en la nube y manos en el PC
Diseño: `docs/superpowers/specs/2026-10-16-jarvis-nube-y-manos-design.md` (revisado también por Gemini).

- **Cerebro en la nube:** Claude Haiku (`cc/claude-haiku-5-5`) a través de OmniRoute, con respuesta en
  streaming (habla frase a frase). Si falla o no responde en 4 s, usa `auto/best-free` de OmniRoute; sin
  internet, Ollama con un modelo ligero (`OLLAMA_MODEL_RESPALDO=granite4.1:8b`). Ollama ya no se carga al arrancar.
- **Programas y carpetas:** abre cualquier programa del menú Inicio y de la tienda (205 en este PC) y
  carpetas por su nombre ("descargas", "documentos"...).
- **Archivos:** busca, lista y lee archivos (texto, PDF, Word) solo dentro de tus carpetas
  (`CARPETAS_PERMITIDAS`). Rutas resueltas antes de comprobarlas (enlaces, junctions, `..`); nunca
  `Windows`, `Program Files`, `AppData`, `.ssh`, `.env`. No descarga archivos que solo están en OneDrive.
- **Internet:** `buscar_web` (DuckDuckGo, 0,75 s) y Claude redacta la respuesta.
- **Tareas grandes:** `encargar_tarea` las hace Claude Code (`cc/claude-sonnet-5-5`) en segundo plano.
  Jarvis repite la tarea exacta y solo empieza si dices "sí"/"adelante" (lo comprueba el código, no la IA).
  Claude Code solo puede leer, buscar, editar y escribir en la carpeta de trabajo (sin consola libre),
  15 minutos como máximo. Aviso por voz al terminar.
- **Seguridad:** lo que llega de archivos, correos, Drive e internet va marcado como `<contenido_no_fiable>`
  y la IA no sigue instrucciones de ahí. Tras leerlo, 3 minutos sin abrir enlaces ni encargar tareas.

**Comprobado:** 32 pruebas automáticas (`pruebas_unidad.py`). Jarvis real en modo texto: conversación,
hora, abrir Bloc de notas y Descargas, búsqueda web del tiempo, y una tarea completa (encargo → "sí" →
Claude Code crea el archivo → aviso). Latencia media 0,93 s en 10 frases. Tras 5 min sin uso la primera
respuesta tardaba 3,3 s: Jarvis mantiene la conexión despierta con un aviso de 1 token cada 4 min de inactividad.
Texto UTF-16 legible y el contenido externo no puede cerrar su marca (hallazgos de la revisión final).
**Sin comprobar todavía:** con la voz y la ventana 3D abiertas.

## [1.4.0] - 16/10/2026 - Autorreparación y registro de errores
Aprobadas: P1, P2 y P6.

**P1 - Autorreparación continua**
- *Voz:* si se cae, Jarvis lo anota, avisa y la levanta solo. Espera 5, 10, 20... hasta 60 s entre
  intentos y vuelve a 5 s tras 5 minutos estable. Saluda solo la primera vez. Mientras tanto se puede escribir.
  Si el problema es de configuración (falta una clave o una librería) no reintenta en bucle: lo dice.
- *Micrófono vigilado mientras funciona:* si deja de enviar audio (desconectado) o lleva 3 minutos
  en silencio absoluto (silenciado), Jarvis busca otro micrófono y sigue.
- *Ollama:* si está cerrado, Jarvis lo abre solo (un intento por minuto). Si sigue fallando, pasa a
  Claude (si hay clave y saldo). Ambas cosas quedan anotadas.
- *Google:* cada 30 minutos comprueba y renueva el permiso. Si se pierde, lo dice una vez por voz
  ("ejecute conectar Google"). Si vuelve, lo anota.

**P2 - Registro de errores** (`registro.py` → `errores_log.txt`)
- Cada fallo queda anotado con fecha, origen (voz, micrófono, ia, google, herramienta, altavoces,
  interfaz...), qué pasó y qué hizo Jarvis para arreglarlo. Se anotan también los errores no previstos
  y los de los hilos internos.
- No guarda lo que dices, ni correos ni notas. Se rota solo al pasar de 1 MB (`errores_log.anterior.txt`).

**P6 - Control de versiones con git**
- Repositorio local en `E:\jarvis` con una etiqueta por versión (`v1.3.1`, `v1.4.0`...).
- Fuera del repositorio: `.env`, `google\` (claves), `cerebro\` (tus notas), `venv\` y registros.
- Volver a una versión anterior: `git checkout v1.3.1` (y `git checkout main` para volver a la última).

**Comprobado:** 15 pruebas con fallos forzados (voz caída 3 veces, micrófono desconectado y mudo,
configuración rota, Google perdido y recuperado, Ollama cerrado, error en un hilo, rotación del
registro). Jarvis real en modo texto con Ollama y Google responde bien. Las pruebas de Google
de la 1.3.0 siguen pasando.
**Sin comprobar todavía:** una caída real de la voz con el micrófono y los altavoces (necesita la ventana abierta).

## [1.3.1] - 16/10/2026 - Autorreparación del micrófono
**Problema:** Jarvis dejó de responder por voz. El micrófono predeterminado de Windows (cámara OBSBOT
Tiny 2 Lite) entregaba silencio absoluto (nivel 0,0000; esta mañana medía 0,0007 de ruido normal).
Jarvis lo usaba sin comprobarlo, así que escuchaba silencio sin avisar. Unos minutos después la
OBSBOT volvió a captar sonido sola, así que fue un silencio temporal (micrófono silenciado o bloqueado).

**Cambios** (`jarvis.py`):
- Al arrancar la voz, Jarvis comprueba que el micrófono recibe sonido.
- Si está mudo, prueba los demás micrófonos, usa el que funcione y lo dice en pantalla.
- Si ninguno funciona, lo avisa (revisar silencio y permiso de micrófono de Windows) en vez de quedarse callado.
- Nuevo ajuste opcional `MICROFONO=parte del nombre` en `ajustes.env` para fijar un micrófono concreto.

**Comprobado:** con el equipo real se simuló un micrófono predeterminado mudo: elige "Micrófono (Realtek
USB Audio)" y avisa. Con todos mudos, avisa sin bloquearse. Con la OBSBOT funcionando se mantiene la OBSBOT.

## [1.3.0] - 16/10/2026 - Google Drive y envío de correo
- Gmail: nueva herramienta `correo_enviar` (enviar y responder dentro del mismo hilo). Se mantienen los borradores.
- Drive: `drive_buscar`, `drive_leer` (Docs, Hojas, Presentaciones, PDF, Word, txt) y `drive_crear_documento`.
- Seguridad: lo leído en correos y archivos se marca como DATOS, nunca como órdenes. Tras leer
  un correo o un archivo de Drive no se abren enlaces durante 3 minutos.
- Permisos de Google ampliados (gmail.send, drive). Un permiso antiguo sin ellos obliga a reconectar.
- `conectar_google.py` comprueba también Drive y muestra el enlace de autorización si el navegador no se abre.
- Proyecto de Google Cloud configurado: APIs activadas, pantalla de consentimiento "Jarvis" en modo
  Prueba con tu cuenta como tester, cliente OAuth de escritorio y `google\credentials.json`.

**Comprobado:** pruebas con Google simulado (enviar, responder en hilo, Drive buscar/leer/crear) y
conexión real: Calendario, Gmail y Drive OK (16/10/2026 16:24).

## [1.2.0] - 16/10/2026 - Google Calendar y Gmail
- `google_conector.py`: ver y crear eventos; buscar, leer y crear borradores de correo.
- Panel "Google" en la ventana 3D y `conectar_google.bat` para autorizar.

## [1.1.0] - 16/10/2026 - Velocidad
- Respuesta media de 3,2 s a 1,5 s: transcripción en vivo, modelo qwen3.8:27b, voz frase a frase
  con ElevenLabs flash y ventana 3D limitada a 60 fps.
- Detecta cuando la IA dice "lo he guardado" sin hacerlo y la obliga a hacerlo.
- Herramientas `diagnostico.bat`, `prueba_auto.bat` y `modelos.bat`.

## [1.0.0] - 15/10/2026 - Primera versión
- Asistente de voz: ElevenLabs (oír y hablar) + IA local Ollama o Claude.
- Segundo cerebro en `cerebro\` (notas, diario, documentos; compatible con Obsidian).
- Ventana 3D con orbe, abrir aplicaciones y webs, hora.

---

## Pendiente de aprobación
Propuestas ordenadas por impacto. Di cuáles apruebas (por ejemplo "apruebo P1, P2 y P4") y se
implementan, se prueban y se anotan aquí como nueva versión.

*(P1, P2 y P6 aprobadas e implementadas en la 1.4.0.)*

**P3. "Jarvis, ¿estás bien?" / autodiagnóstico por voz**
Que ejecute el diagnóstico y te diga en una frase qué falla y cómo lo ha arreglado o qué debes hacer tú.

**P4. Avisos proactivos**
Que te avise 10 minutos antes de cada cita del calendario, y un resumen por la mañana (agenda del
día y correos importantes) cuando lo pidas o a una hora fija.

**P5. Memoria más inteligente**
Ahora el cerebro busca por palabras exactas. Con búsqueda por significado (modelo de embeddings local
en Ollama), "¿qué ideas tenía para YouTube?" encontraría la nota "canal de IA para principiantes".

**P7. Prueba automática antes de cada versión**
Ampliar `prueba_auto.bat` para que pruebe también Google (simulado), el micrófono y la voz, y
ejecutarla antes de dar por buena cada versión.

**P8. Confirmación por voz para acciones delicadas** *(opcional)*
Ahora Jarvis envía correos sin confirmar, como elegiste. Opción: que solo pida "¿lo envío?" cuando el
destinatario sea alguien con quien nunca te has escrito.
