# JARVIS + Segundo Cerebro

Asistente de voz con memoria a largo plazo e interfaz 3D, funcionando en tu PC.

    Tu voz -> ElevenLabs (te entiende mientras hablas) -> IA local Ollama (qwen3.8:27b en tu RTX 4090)
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

## Velocidad medida en este PC (16/10/2026)
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

## Ajustes
- `.env`: tus claves (ElevenLabs, Anthropic). No lo compartas.
- `ajustes.env`: ajustes sin claves. Ahora: `OLLAMA_MODEL=qwen3.8:27b`, `TTS_MODEL=eleven_flash_v2_5`.
  Otras opciones: `STT_VIVO=0` (transcripcion clasica), `LLM_PROVEEDOR=anthropic` (usar Claude,
  necesita saldo de API), `INTERFAZ=clasica` (ventana simple), `WAKE_WORD=...`,
  `MICROFONO=Realtek` (fija un micrófono por parte de su nombre; si no, Jarvis usa el predeterminado
  y, si está mudo, cambia solo a otro que funcione).
- Historial de versiones y mejoras pendientes de aprobar: `CHANGELOG.md`.
- Si algo falla, mira `errores_log.txt`: cada fallo, qué lo causó y qué hizo Jarvis para arreglarlo.
- Cada versión está guardada con git: `git tag` las lista y `git checkout v1.3.1` vuelve a una anterior.

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
    llm.py           IA: Ollama y Claude, herramientas, correccion de respuestas
    memoria.py       Segundo cerebro (guardar, buscar, importar documentos)
    interfaz_web.py  Servidor local de la ventana 3D (solo accesible desde tu PC, con clave)
    ui\              Ventana 3D (Three.js)
    cerebro\         Tus notas: inbox\, notas\, diario\, documentos\
