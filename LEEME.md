# JARVIS + Segundo Cerebro

Asistente de voz con memoria a largo plazo e interfaz 3D, funcionando en tu PC.

    Tu voz -> ElevenLabs (te entiende mientras hablas) -> Claude Haiku en la nube, a traves de OmniRoute
           (si falla: modelo gratuito de OmniRoute; sin internet: Ollama granite4.1:8b en tu PC)
           -> ElevenLabs (voz "Jarvis", modelo flash) -> altavoces
    Lo que recuerda se guarda en cerebro\ como notas de texto (compatibles con Obsidian).

## Uso diario
- Doble clic en `jarvis.bat` (o en el acceso directo "Jarvis" del escritorio, si lo creas con
  `crear_acceso_directo.bat`).
- Se abre la ventana 3D. Dile "Jarvis, ..." o escribe en la caja de abajo.
- Tras una respuesta tienes 10 segundos para seguir hablando sin repetir "Jarvis".
- Para apagarlo: cierra la ventana o di "Jarvis, adios". F11 = pantalla completa.

Colores del orbe: azul = en espera, verde = te escucha, ambar = piensa, cian = habla,
rojo = el microfono no funciona (puedes seguir escribiendo).

Ejemplos:
- "Jarvis, apunta en el diario que el viernes tengo dentista a las cinco."
- "Jarvis, guarda esta idea: un canal sobre IA para principiantes."
- "Jarvis, que tengo apuntado para el viernes?"
- "Jarvis, que he apuntado esta semana?"
- "Jarvis, abre la calculadora." / "Jarvis, busca en Google recetas de lentejas."
- "Jarvis, procesa la bandeja."  (tras dejar PDF o Word en cerebro\inbox)
- "Jarvis, abre Excel." / "Jarvis, abre la carpeta de descargas."  (cualquier programa del menu Inicio)
- "Jarvis, busca el archivo del presupuesto y leemelo."  (solo en tus carpetas: Escritorio, Documentos,
  Descargas, Imagenes, Musica, Videos y OneDrive; se cambian con CARPETAS_PERMITIDAS en ajustes.env)
- "Jarvis, busca en internet que tiempo hara mañana."
- "Jarvis, encarga una tarea: ordena los PDF de descargas en carpetas por año."  Jarvis te repite la
  tarea y espera a que digas "si" o "adelante". La hace Claude Code en segundo plano (por defecto en
  Documentos\Jarvis\tareas) y te avisa al terminar. "Jarvis, como va la tarea?" / "cancela la tarea".
- "Jarvis, programa un script en Documentos\proyectos\fotos que renombre las fotos por fecha, con pruebas."
  Modo programador (v1.7): Claude Code escribe el codigo, lo ejecuta, pasa las pruebas y hace commits en una
  rama nueva (nunca sube nada a internet). Despues: "Jarvis, ahora añade que tambien ordene por carpetas"
  continua la misma tarea con todo lo que ya sabe. Siempre te pide "si" antes de empezar.

## Velocidad con Claude en la nube (v1.5, 16/10/2026)
Tiempo hasta la primera palabra de la respuesta, 10 frases reales: **0,93 s de media** (0,74 s el mejor
caso, 1,41 s el peor). Al arrancar, Jarvis abre la conexion con la nube (unos 5 s, en segundo plano).
Tras 4 minutos sin usarse, la primera respuesta tardaba 3,3 s: por eso Jarvis manda un aviso minimo
(1 token) a la nube cuando lleva 4 minutos parado, y asi responde siempre rapido.

## Velocidad medida en este PC con Ollama (16/10/2026, v1.4)
Tiempo desde que te callas hasta que Jarvis empieza a hablar: **1,5 s de media** (0,9 s el mejor caso).
Al empezar la noche era 3,2 s. Lo que lo consigue:
- Transcripcion en vivo (tu voz se envia mientras hablas): 0,2 s en vez de 0,5-1,3 s.
- Modelo qwen3.8:27b: 70 tok/s y usa bien las herramientas (qwen2.5:32b iba a 29 tok/s y a veces
  decia "lo he apuntado" sin apuntar nada).
- Habla frase a frase mientras la IA escribe; voz ElevenLabs "flash" (0,23 s en vez de 1 s).
- Si la IA dice que ha guardado algo sin hacerlo, Jarvis lo detecta y la obliga a hacerlo.
- La ventana 3D se limita a 60 fps (30 mientras piensa) para no quitarle grafica a la IA.

## Herramientas incluidas
| Archivo | Para que sirve |
|---|---|
| `jarvis.bat` | Arranca Jarvis |
| `instalar.bat` | Instalacion inicial (Python, paquetes y modelo de IA segun tu grafica) |
| `actualizar.bat` | Instala paquetes nuevos tras una actualizacion |
| `diagnostico.bat` | Revisa grafica, Ollama, ElevenLabs, microfono... -> `diagnostico.txt` |
| `prueba_auto.bat` | Prueba completa y silenciosa con preguntas reales; mide tiempos -> `prueba_auto.txt` |
| `modelos.bat` | Compara modelos de Ollama (aciertos y velocidad) -> `modelos.txt` |
| `crear_acceso_directo.bat` | Crea el icono "Jarvis" en el escritorio |
| `jarvis_texto.bat` | Modo texto en la consola, sin voz ni ventana (para pruebas) |

`jarvis_log.txt` guarda el tiempo de cada respuesta.

## Requisitos de la v1.5
- OmniRoute abierto en tu PC (http://localhost:20128) con `ANTHROPIC_BASE_URL` y `ANTHROPIC_AUTH_TOKEN`
  en `.env`. Modelo: `CLAUDE_MODEL=cc/claude-haiku-5-5`.
- Para encargar tareas: Claude Code (`npm install -g @anthropic-ai/claude-code`). `diagnostico.bat` lo comprueba.
- Pruebas rapidas sin voz: `venv\Scripts\python.exe -m unittest pruebas_unidad -v`

## Ajustes
- `.env`: tus claves (ElevenLabs, Anthropic, token de OmniRoute). No lo compartas.
- `ajustes.env`: ajustes sin claves. Ahora: `OLLAMA_MODEL=qwen3.8:27b`, `TTS_MODEL=eleven_flash_v2_5`.
  Otras opciones: `STT_VIVO=0` (transcripcion clasica), `LLM_PROVEEDOR=anthropic` (usar Claude,
  necesita saldo de API), `INTERFAZ=clasica` (ventana simple), `WAKE_WORD=...`,
  `MICROFONO=Realtek` (fija un micrófono por parte de su nombre; si no, Jarvis usa el predeterminado
  y, si está silenciado de verdad, cambia solo a otro que funcione), `UMBRAL_VOZ=0.006` (si no te oye
  cuando hablas bajo; súbelo a 0.02 si se activa con ruidos).
- Historial de versiones y mejoras pendientes de aprobar: `CHANGELOG.md`.
- Si algo falla, mira `errores_log.txt`: cada fallo, qué lo causó y qué hizo Jarvis para arreglarlo.
- Cada versión está guardada con git: `git tag` las lista y `git checkout v1.3.1` vuelve a una anterior.

## WhatsApp, paso a paso
Con esto Jarvis te avisa por WhatsApp (tareas terminadas, citas, recordatorios) y puedes escribirle desde
el movil. Usa el numero de prueba gratuito de Meta como numero de Jarvis; tu numero personal es el unico
destinatario y el unico que Jarvis atiende. Es opcional: sin configurar nada, Jarvis funciona como siempre.
Requiere iniciar sesion y aceptar condiciones, asi que lo haces tu. Tarda un buen rato la primera vez.
Los nombres de pantallas y botones de Meta y ngrok cambian a veces; si alguno no coincide, busca el equivalente.

**Paso 1 - Crear la app en Meta.** Entra en developers.facebook.com con tu cuenta de Facebook y crea una app
de tipo *Business*. Dentro de la app anade el producto *WhatsApp*. Elige o crea una cuenta de WhatsApp Business
cuando te lo pida. En el menu izquierdo, *WhatsApp > API Setup* muestra el *Phone number ID*
(apuntalo: es `WHATSAPP_PHONE_ID`) y el *WhatsApp Business Account ID* (`WHATSAPP_WABA_ID`, opcional).
El *App Secret* (clave secreta de la app) esta en los ajustes basicos de la app, con un boton para mostrarlo:
es `WHATSAPP_APP_SECRET`.

**Paso 2 - Anadir tu numero como destinatario.** En *API Setup*, en el campo *To*, elige anadir un numero de
telefono nuevo y escribe el tuyo. Meta te manda un codigo a tu movil: introducelo. Solo se hace una vez.
Tu numero va en `.env` con prefijo de pais, sin `+` ni espacios (por ejemplo `34600111222`).

**Paso 3 - Token permanente.** El token temporal de *API Setup* (*Generate access token*) caduca en unas
horas: no sirve. En la Configuracion del negocio de Meta (Business Settings) entra en *System users*
(usuarios del sistema), pulsa *Add* y crea uno con rol de administrador. Con ese usuario seleccionado usa
*Assign Assets* para darle control sobre tu app y tu cuenta de WhatsApp. Despues pulsa *Generate token*,
elige tu app, marca los permisos `whatsapp_business_messaging` y `whatsapp_business_management` y copia el
token: es `WHATSAPP_TOKEN`. Solo se muestra una vez.

**Paso 4 - Plantilla `aviso_jarvis`.** Fuera de las 24 h siguientes a tu ultimo mensaje, WhatsApp solo deja
enviar plantillas aprobadas. En el WhatsApp Manager de tu cuenta, en la seccion de plantillas de mensaje,
crea una nueva con estos datos exactos:
- Nombre: `aviso_jarvis`
- Categoria: *Utility* (Utilidad)
- Idioma: *Spanish* (Espanol)
- Cuerpo: `Jarvis: {{1}}` (con una variable; si pide un ejemplo, escribe cualquier frase)

Envia la plantilla y espera a que la aprueben (suele ser rapido). Limitacion conocida: con el numero de
prueba de Meta puede que no deje usar plantillas propias hasta que verifiques una empresa o registres un
numero real. Si es asi, los avisos fuera de las 24 h no llegaran; dentro de las 24 h (si hablaste con Jarvis
hace poco) funcionan igual.

**Paso 5 - ngrok.** ngrok es la puerta por la que Meta llega a tu PC.
1. Crea una cuenta gratuita en ngrok.com.
2. Instala `ngrok.exe` (por ejemplo, en una ventana de comandos: `winget install ngrok.ngrok`, o descargalo de
   ngrok.com). Jarvis lo encuentra en el PATH o en los sitios habituales.
3. En el panel de ngrok (dashboard) busca tu *authtoken* y, en una ventana de comandos, ejecuta
   `ngrok config add-authtoken TU_TOKEN` (con tu token en lugar de TU_TOKEN).
4. En el panel de ngrok, en la seccion de dominios (*Domains*), reserva el dominio estatico gratuito. Te da
   uno como `algo-algo.ngrok-free.app`: es `NGROK_DOMINIO` (sin `https://`).

**Paso 6 - Rellenar `.env`, arrancar y registrar el webhook.**
1. Abre `.env` (no lo compartas) y anade, sin comillas:
   - `WHATSAPP_TOKEN`: el token permanente del paso 3.
   - `WHATSAPP_PHONE_ID`: el Phone number ID del paso 1.
   - `WHATSAPP_MI_NUMERO`: tu numero, con prefijo y sin `+` (paso 2).
   - `WHATSAPP_APP_SECRET`: el App Secret del paso 1.
   - `WHATSAPP_VERIFY_TOKEN`: una frase que inventes tu (por ejemplo `jarvis-clave-casa-2026`).
   - `NGROK_DOMINIO`: tu dominio de ngrok del paso 5.
   - Opcional: `WHATSAPP_WABA_ID` (para que el diagnostico compruebe la plantilla). Hay un ejemplo en `.env.example`.
   - Ajustes opcionales, que van en `ajustes.env` (no en `.env`): `WHATSAPP_PLANTILLA` (por defecto `aviso_jarvis`),
     `WHATSAPP_AVISO_MIN` (minutos de antelacion de los avisos de citas, 15), `WHATSAPP_PUERTO` (8766) y
     `WHATSAPP_API_VERSION`. Solo hace falta tocarlos si cambias algo.
2. Cierra y abre Jarvis con `jarvis.bat`. Al arrancar abre el receptor y ngrok por su cuenta, y los cierra
   al salir.
3. En developers.facebook.com, en tu app, entra en la configuracion de WhatsApp (*WhatsApp > Configuration*),
   en la parte del webhook, y edita el webhook con:
   - Callback URL: `https://TU_DOMINIO/whatsapp` (con tu dominio de ngrok).
   - Verify token: el mismo texto de `WHATSAPP_VERIFY_TOKEN`.
   Guarda/verifica. Jarvis debe estar abierto para contestar a Meta.
4. En esa misma parte, en los campos del webhook (*Webhook fields*), suscribete al campo `messages`.

**Importante:** WhatsApp solo funciona con el PC encendido y Jarvis abierto. Si te escriben mientras esta cerrado,
Meta reintenta un rato, pero Jarvis no guarda esos mensajes ni los recupera despues.

**Comprueba con `diagnostico.bat`.** Abre `diagnostico.txt` y mira la seccion *9. WHATSAPP*: te dice que
variables faltan, si el token y el numero son validos, si la plantilla existe (si pusiste `WHATSAPP_WABA_ID`),
si `ngrok.exe` esta instalado y si tu dominio responde (con Jarvis abierto). Despues escribe "hola" al
numero de Jarvis desde tu movil.

## Grafica y juegos
qwen3.8:27b ocupa ~17 GB de la grafica y se queda cargado 30 minutos tras el ultimo uso.
Antes de un juego exigente cierra Jarvis, o en una ventana de comandos: `ollama stop qwen3.8:27b`.
Modelos que puedes borrar si no los usas (liberan disco): `ollama rm qwen2.5:32b` (20 GB),
`ollama rm granite4.1:8b` (5 GB, alternativa ligera y rapida).

## Obsidian
"Open folder as vault" -> `E:\jarvis\cerebro`. Veras notas, etiquetas y enlaces [[asi]].
Lo que escribas ahi, Jarvis tambien lo encuentra. (`prueba_cerebro\` son notas de las pruebas
automaticas; puedes borrar esa carpeta.)

## Carpetas
    jarvis.py        Programa principal (voz, ventana, herramientas)
    llm.py           IA: Claude (nube) y Ollama, herramientas, respaldos, correccion de respuestas
    pc.py            Abrir programas y carpetas; buscar, listar y leer archivos (solo carpetas permitidas)
    web.py           Busqueda en internet (DuckDuckGo)
    tareas.py        Encargar tareas grandes a Claude Code, con confirmacion por voz
    memoria.py       Segundo cerebro (guardar, buscar, importar documentos)
    interfaz_web.py  Servidor local de la ventana 3D (solo accesible desde tu PC, con clave)
    ui\              Ventana 3D (Three.js)
    cerebro\         Tus notas: inbox\, notas\, diario\, documentos\
