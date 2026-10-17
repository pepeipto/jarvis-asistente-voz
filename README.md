# JARVIS — Asistente de voz con segundo cerebro (Windows y macOS)

Asistente de voz en español que funciona en tu PC: le hablas ("Jarvis, ..."), te entiende mientras
hablas, piensa con una IA (local con Ollama o en la nube con Claude) y te responde con voz, frase a frase.
Guarda lo que le pides en un **segundo cerebro** de notas en texto (compatible con Obsidian) y se conecta
con Google Calendar, Gmail y Drive. Tiene una interfaz 3D (un orbe animado con Three.js).

> Guía de uso diario en español: [LEEME.md](LEEME.md) · Historial de versiones: [CHANGELOG.md](CHANGELOG.md)

## Qué hace
- **Voz en tiempo real**: transcripción en vivo con ElevenLabs (o Whisper local) y voz con ElevenLabs
  (modelo *flash*). Palabra de activación configurable y 10 s para seguir hablando sin repetirla.
- **Cerebro de IA intercambiable**: Ollama local (por ejemplo `qwen3.8:27b`) o Claude (API de Anthropic
  directa o a través de un proxy compatible como OmniRoute, con `ANTHROPIC_BASE_URL`).
  Si un proveedor falla pasa solo al otro.
- **Segundo cerebro**: notas, diario y documentos en Markdown (`cerebro/`). Busca antes de responder,
  enlaza personas y proyectos con `[[enlaces]]` e importa PDF y Word dejados en `cerebro/inbox`.
- **Google**: consultar y crear citas, buscar, leer, redactar y enviar correos, buscar y leer archivos
  de Drive y crear Google Docs.
- **PC**: abrir aplicaciones y páginas web, buscar en Google, decir la hora.
- **Autorreparación**: si se cae la voz, el micrófono queda mudo, Ollama está cerrado o se pierde el
  permiso de Google, lo detecta, lo arregla si puede y lo anota en `errores_log.txt`.
- **Seguridad**: el contenido de notas, correos y documentos se trata como datos, no como órdenes;
  no abre enlaces justo después de leer correos; la interfaz web solo escucha en tu PC y con clave.

Velocidad medida (RTX 4090, Ollama `qwen3.8:27b`): **1,5 s de media** desde que te callas hasta que
empieza a hablar.

## Requisitos
- Windows 10/11 o macOS (Apple Silicon recomendado), Python 3.10-3.13 y Chrome, Edge o Brave (para la ventana 3D).
- Cuenta de [ElevenLabs](https://elevenlabs.io) (voz y transcripción).
- Al menos un cerebro de IA:
  - [Ollama](https://ollama.com) con un modelo que use herramientas (el instalador elige uno según tu
    gráfica), o
  - Claude: clave de API de Anthropic, o un proxy compatible (por ejemplo OmniRoute en local).
- Opcional: proyecto de Google Cloud con OAuth de escritorio para Calendar, Gmail y Drive.

## Instalación
1. Clona el repositorio y ejecuta `instalar.bat` (crea `venv`, instala `requirements.txt` y, si usas
   Ollama, descarga un modelo adecuado a tu gráfica).
2. Copia `.env.example` como `.env` y rellena tus claves. Los ajustes sin claves están en `ajustes.env`.
3. (Opcional) Google: guarda tu `credentials.json` de OAuth en `google/` y ejecuta `conectar_google.bat`.
4. Arranca con `jarvis.bat` (o `crear_acceso_directo.bat` para tener el icono en el escritorio).

`diagnostico.bat` revisa gráfica, Ollama, ElevenLabs, micrófono y Google y deja el informe en
`diagnostico.txt`.

### Instalación en macOS
1. `git clone https://github.com/pepeipto/jarvis-asistente-voz && cd jarvis-asistente-voz`
   (si usas la rama de pruebas: `git checkout soporte-mac`).
2. Necesitas Python (`brew install python@3.12`) y un navegador Chrome, Edge o Brave.
3. Ejecuta `./instalar.command` (o doble clic). Crea `venv`, instala paquetes y propone un modelo de
   Ollama según la memoria del Mac (32 GB o más: `qwen3.8:27b`; menos: `granite4.1:8b`).
4. Copia `.env.example` como `.env` y rellena las claves. Arranca con `./jarvis.command`.
5. La primera vez macOS pide permiso de **micrófono** para Terminal: pulsa Permitir (Ajustes del Sistema >
   Privacidad y seguridad > Micrófono).
Los demás scripts tienen la misma versión `.command` que el `.bat` de Windows (`diagnostico`, `actualizar`,
`conectar_google`, `modelos`, `prueba_auto`, `jarvis_texto`, `crear_acceso_directo`).

**Usar el Ollama de otro equipo** (por ejemplo el PC con la RTX 4090 desde el Mac): en el PC define
`OLLAMA_HOST=0.0.0.0` y reinicia Ollama (abre el puerto 11434 solo en tu red local), y en el Mac pon en `.env`
`OLLAMA_URL=http://IP-DEL-PC:11434`. Ollama no tiene clave: no lo expongas a internet.

## Configuración (`.env` / `ajustes.env`)
| Variable | Para qué |
|---|---|
| `LLM_PROVEEDOR` | `auto` (Ollama y, si falla, Claude), `ollama` o `anthropic` |
| `OLLAMA_MODEL` | Modelo de Ollama; vacío = elige el mejor de los descargados |
| `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | Claude por la API de Anthropic |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` | Claude a través de un proxy (p. ej. OmniRoute); solo se envía el token |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TTS_MODEL` | Voz |
| `STT_MODE`, `STT_VIVO` | Transcripción: `elevenlabs` o `local`; en vivo sí/no |
| `WAKE_WORD`, `MICROFONO`, `INTERFAZ` | Palabra de activación, micrófono fijo, `web` o `clasica` |
| `CEREBRO_DIR` | Carpeta del segundo cerebro (por defecto `cerebro/`) |
| `OLLAMA_URL` | Dirección de Ollama (por defecto `http://127.0.0.1:11434`; puede ser otro equipo de tu red) |

## Estructura
| Archivo | Responsabilidad |
|---|---|
| `jarvis.py` | Programa principal: voz, ventana, herramientas del PC y bucle de conversación |
| `llm.py` | Cerebro de IA: Ollama y Claude con herramientas, respaldo entre proveedores y corrección de respuestas |
| `memoria.py` | Segundo cerebro: guardar, buscar e importar documentos |
| `google_conector.py`, `conectar_google.py` | Calendar, Gmail y Drive (OAuth) |
| `interfaz_web.py`, `ui/` | Ventana 3D local (Three.js) |
| `interfaz.py` | Ventana clásica sencilla |
| `plataforma.py` | Diferencias Windows/macOS (nombre de los scripts, etc.) |
| `registro.py` | Registro de errores con rotación |
| `diagnostico.py`, `prueba_auto.py`, `modelos.py` | Diagnóstico, prueba de extremo a extremo silenciosa y comparativa de modelos |
| `docs/superpowers/` | Diseños y planes de las próximas versiones |

## Privacidad
Fuera del repositorio (ver `.gitignore`): `.env` (claves), `google/` (permisos de Google), `cerebro/`
(tus notas), registros y entornos. El registro de errores no guarda lo que dices, ni correos ni notas.

## Próxima versión (1.5, en desarrollo)
Claude Haiku como cerebro principal a través de OmniRoute con streaming y respaldos, abrir cualquier
programa instalado, buscar y leer archivos del PC, búsqueda web y encargar tareas grandes a Claude Code
con confirmación por voz. Diseño: [docs/superpowers/specs](docs/superpowers/specs).
