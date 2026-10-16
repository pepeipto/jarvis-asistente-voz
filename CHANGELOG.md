# Registro de cambios de Jarvis

Cada versión anota qué cambió, por qué y cómo se comprobó.
Formato: **MAYOR.MENOR.PARCHE**
- MAYOR: cambia la forma de usar Jarvis.
- MENOR: funciones nuevas.
- PARCHE: arreglos.

Las mejoras propuestas esperan en **Pendiente de aprobación** (al final) hasta que digas "sí" a cada una.

---

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

**P1. Autorreparación continua (vigilante)** - *muy recomendada*
Ahora, si el bucle de voz falla una vez, la voz queda apagada hasta reiniciar Jarvis. Propuesta:
- Reintentar la voz automáticamente.
- Vigilar el micrófono también mientras funciona (si se queda mudo, cambiar a otro).
- Si Ollama no responde, pasar a Claude (si hay saldo) y volver después.
- Avisar por voz cuando caduque el permiso de Google.

**P2. Registro de errores** - *muy recomendada*
Hoy los errores solo salen en la consola y se pierden. Por eso no se podía saber por qué no respondía.
Propuesta: `errores_log.txt` con fecha, qué falló y qué hizo Jarvis para arreglarlo.

**P3. "Jarvis, ¿estás bien?" / autodiagnóstico por voz**
Que ejecute el diagnóstico y te diga en una frase qué falla y cómo lo ha arreglado o qué debes hacer tú.

**P4. Avisos proactivos**
Que te avise 10 minutos antes de cada cita del calendario, y un resumen por la mañana (agenda del
día y correos importantes) cuando lo pidas o a una hora fija.

**P5. Memoria más inteligente**
Ahora el cerebro busca por palabras exactas. Con búsqueda por significado (modelo de embeddings local
en Ollama), "¿qué ideas tenía para YouTube?" encontraría la nota "canal de IA para principiantes".

**P6. Control de versiones con git**
Guardar cada versión para poder volver atrás en un segundo si un cambio sale mal.
Cada versión de este registro quedaría asociada a un punto de restauración.

**P7. Prueba automática antes de cada versión**
Ampliar `prueba_auto.bat` para que pruebe también Google (simulado), el micrófono y la voz, y
ejecutarla antes de dar por buena cada versión.

**P8. Confirmación por voz para acciones delicadas** *(opcional)*
Ahora Jarvis envía correos sin confirmar, como elegiste. Opción: que solo pida "¿lo envío?" cuando el
destinatario sea alguien con quien nunca te has escrito.
