# Registro de cambios de Jarvis

Cada versión anota qué cambió, por qué y cómo se comprobó.
Formato: **MAYOR.MENOR.PARCHE**
- MAYOR: cambia la forma de usar Jarvis.
- MENOR: funciones nuevas.
- PARCHE: arreglos.

Las mejoras propuestas esperan en **Pendiente de aprobación** (al final) hasta que digas "sí" a cada una.

---

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
