# Jarvis v1.6 — WhatsApp (API oficial de Meta)

Fecha: 2026-10-16 · Estado: pendiente de revisar por el usuario

## Objetivo
Poder hablar con Jarvis por WhatsApp desde el móvil cuando no estás delante del PC, y que Jarvis te
escriba por WhatsApp para avisarte de cosas.

Criterios de éxito:
- Le escribes desde tu móvil y contesta por WhatsApp en ≤ 10 s (con el PC encendido y Jarvis abierto).
- Te avisa del fin de las tareas, 15 min antes de tus citas, de lo que le pidas por voz y de los
  problemas que no puede arreglar solo, aunque lleves más de 24 h sin escribirle.
- Ningún mensaje de otro número ni sin la firma de Meta llega a la IA.
- Nada que envíe, cree o ejecute algo se hace desde WhatsApp sin un «sí» tuyo en el chat.
- Si WhatsApp o ngrok fallan, Jarvis sigue funcionando por voz como hoy.

## Decisiones tomadas con el usuario
- API oficial: **WhatsApp Cloud API de Meta**, con el **número de prueba gratuito** de Meta como número
  de Jarvis (hasta 5 destinatarios verificados y sin verificar una empresa). Tu número personal es el
  único destinatario y el único remitente aceptado.
- Entrada desde internet: **ngrok** con su dominio fijo gratuito (`xxx.ngrok-free.app`).
- Desde el móvil: **todo menos lo delicado**, y lo delicado solo con confirmación.
- Avisos: fin de tareas, recordatorio de citas, a petición por voz y problemas sin reparar.

## Supuestos (corregir si no son así)
- Solo funciona con el PC encendido y Jarvis abierto. Los mensajes que lleguen con Jarvis cerrado los
  reintenta Meta durante un tiempo; Jarvis no los guarda ni los recupera después.
- Desde WhatsApp responde con texto, no con notas de voz.
- Los mensajes que no son de texto (audio, fotos, ubicación) se contestan con «Por ahora solo leo texto».

## Arquitectura
Todo dentro del proceso de Jarvis (enfoque A). Un único módulo nuevo, `whatsapp.py`, con el mismo
patrón que `google_conector.py` y `tareas.py` (`HERRAMIENTAS` + `ejecutar()`), y cambios pequeños en
`jarvis.py`, `diagnostico.py`, `.env.example`, `.gitignore` y la documentación.

### `whatsapp.py`
**Configuración** (`.env`, nunca en git):

| Variable | Para qué |
|---|---|
| `WHATSAPP_TOKEN` | Token permanente de un usuario del sistema de Meta Business |
| `WHATSAPP_PHONE_ID` | ID del número de Jarvis (el de prueba de Meta) |
| `WHATSAPP_MI_NUMERO` | Tu número, con prefijo y sin `+` ni espacios (p. ej. `34600111222`) |
| `WHATSAPP_APP_SECRET` | Secreto de la app de Meta, para comprobar la firma de cada mensaje |
| `WHATSAPP_VERIFY_TOKEN` | Texto que eliges tú y pones también en Meta al registrar el webhook |
| `NGROK_DOMINIO` | Tu dominio fijo de ngrok (`xxx.ngrok-free.app`) |

En `ajustes.env` (sin claves): `WHATSAPP_PUERTO=8766`, `WHATSAPP_AVISO_MIN=15`,
`WHATSAPP_PLANTILLA=aviso_jarvis`, `WHATSAPP_API_VERSION` (versión de la Graph API; se fija a la vigente
al implementar).

Si falta `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` o `WHATSAPP_MI_NUMERO`, WhatsApp queda desactivado
sin errores. Si falta `WHATSAPP_APP_SECRET`, no se arranca el receptor: sin firma no se acepta nada.

**Enviar** — `enviar(texto)`:
- Si tu último mensaje llegó hace menos de 24 h (la ventana de servicio de Meta): mensaje de texto
  libre (`POST /{PHONE_ID}/messages`, `type=text`).
- Si no: la plantilla `aviso_jarvis` (categoría utilidad, español, cuerpo `Jarvis: {{1}}`) con el
  texto como parámetro.
- Si Meta rechaza el texto libre por estar fuera de la ventana, se reintenta con la plantilla.
- El momento de tu último mensaje se guarda en `whatsapp_estado.json` para que la ventana de 24 h
  sobreviva a un reinicio.
- Textos de más de 4096 caracteres se parten en varios mensajes. El `**negrita**` de la IA se pasa a
  `*negrita*` de WhatsApp.
- Errores de red o de Meta: se anotan en `errores_log.txt` y `enviar` devuelve False; nunca lanza
  una excepción hacia quien lo llama.

**Recibir** — servidor HTTP en `127.0.0.1:WHATSAPP_PUERTO` (solo local; ngrok lo publica):
- `GET /whatsapp`: verificación del webhook de Meta (`hub.mode=subscribe`, `hub.verify_token`
  igual a `WHATSAPP_VERIFY_TOKEN` → devuelve `hub.challenge`; si no, 403).
- `POST /whatsapp`:
  1. Comprueba la cabecera `X-Hub-Signature-256` (HMAC-SHA256 del cuerpo exacto con
     `WHATSAPP_APP_SECRET`, comparado en tiempo constante). Si no cuadra, 403 y se anota.
  2. Responde 200 al momento y procesa en un hilo aparte (Meta reintenta si tardas).
  3. Ignora los avisos de estado (entregado, leído) y los mensajes repetidos (por id, se recuerdan
     los últimos 200).
  4. Si el remitente no es `WHATSAPP_MI_NUMERO`: se descarta sin responder y se anota solo el hecho,
     sin el contenido.
  5. Como máximo 20 mensajes por minuto; el resto se descarta y se anota.
  6. Entrega el texto a `al_recibir(texto)`, que conecta `jarvis.py`.

**ngrok**:
- Si `NGROK_DOMINIO` está configurado y se encuentra `ngrok.exe` (en el PATH o en las rutas típicas
  de instalación), se lanza `ngrok http --url=https://<dominio> <puerto>` sin ventana al arrancar
  Jarvis.
- Se cierra al salir de Jarvis, antes del `os._exit`.
- Si ngrok no está o falla, se anota y Jarvis lo dice una vez por voz. Si ya hay otro ngrok
  publicando ese dominio, se respeta y no se lanza otro.

### Conversación desde el móvil (en `jarvis.py`)
- **Una IA propia para WhatsApp**: un segundo `llm.IA` con el mismo cerebro, configuración y
  contexto, pero con un historial separado del de voz y con las herramientas filtradas. Se usa el
  mismo `lock_cerebro` que la voz, para que nunca respondan las dos a la vez.
- El prompt de sistema lleva una línea extra: «Hablas por WhatsApp: respuestas breves, sin abrir
  programas ni webs; el usuario no está delante del PC».
- **Herramientas permitidas**:
  - notas y diario (`guardar_nota`, `anadir_al_diario`, `buscar_en_cerebro`, `leer_nota`,
    `notas_recientes`, `procesar_bandeja`);
  - agenda (`calendario_eventos`);
  - correo (`correo_buscar`, `correo_leer`, `correo_borrador`);
  - Drive (`drive_buscar`, `drive_leer`);
  - web y archivos (`buscar_web`, `buscar_archivos`, `leer_archivo`, `listar_carpeta`);
  - hora y recordatorios (`hora_actual`, `whatsapp_recordar`);
  - tareas (`estado_tarea`, `cancelar_tarea`).
- **Quitadas**: `abrir_programa`, `abrir_carpeta`, `abrir_web` y `whatsapp_enviar` (ya estás en
  WhatsApp).
- **Con confirmación**: `correo_enviar`, `calendario_crear`, `drive_crear_documento` y `encargar_tarea`.
  - `encargar_tarea` usa la confirmación que ya tiene `tareas.py`, incluido el bloqueo de 180 s tras
    leer contenido externo. Antes de preguntar a la IA, la respuesta de WhatsApp pasa por
    `tareas.respuesta_confirmacion`, igual que la voz.
  - Las otras tres las intercepta el `run_tool` de WhatsApp:
    1. No las ejecuta: guarda la acción pendiente (herramienta y argumentos) y devuelve a la IA
       «Pendiente de confirmación: resume al usuario exactamente lo que se va a hacer y pídele que
       conteste sí».
    2. Tu siguiente mensaje lo decide el código, no la IA. Con «sí» (mismas palabras que `tareas._SI`)
       ejecuta la acción y te contesta con el resultado. Con «no» (`tareas._NO`) la cancela. Con
       cualquier otra cosa la cancela y se procesa como mensaje normal.
    3. La acción pendiente caduca a los 5 min. Solo puede haber una.
- Si todas las IA fallan, te contesta «Ahora mismo no puedo pensar; inténtalo en un rato» y se anota.
- Cada mensaje y respuesta aparece también en la ventana de Jarvis como `[WhatsApp] …`, para que lo
  veas si estás en el PC.

### Avisos de Jarvis
Todos pasan por `whatsapp.enviar` y se anotan en `errores_log.txt` como `[whatsapp] aviso enviado`
(sin el texto).
- **Fin de tareas**: `tareas.on_fin` llama además a `whatsapp.enviar`.
- **Citas**: un hilo `vigilante_citas` cada minuto pide a Google los eventos de los próximos
  `WHATSAPP_AVISO_MIN` minutos y avisa una vez por evento: «En 15 min: <título> (<hora>)».
  - Los eventos ya avisados (id + hora de inicio) se guardan en `whatsapp_estado.json` para no
    repetir tras un reinicio, y se limpian pasadas 24 h.
  - Los eventos de día completo no se avisan.
  - Sin permiso de Google, el hilo no hace nada.
- **A petición por voz** — dos herramientas nuevas (también para la IA de voz):
  - `whatsapp_enviar(texto)`: «mándame esto al móvil». Envía al momento a tu número; no lleva
    destinatario como argumento, así que no puede escribir a nadie más.
  - `whatsapp_recordar(texto, cuando)`: «recuérdame a las 6 por WhatsApp…». `cuando` va en formato
    ISO local, y la IA convierte «mañana a las 6» con la fecha del contexto, como ya hace con el
    calendario.
    - Los recordatorios se guardan en `whatsapp_recordatorios.json` y un hilo los revisa cada 30 s.
    - Al reiniciar, los atrasados de menos de 12 h se envían con «(con retraso)» y los más antiguos
      se descartan.
- **Problemas sin reparar**: nueva función `jarvis.aviso_grave(texto)`, que llama a `aviso` y a
  `whatsapp.enviar`, como máximo una vez cada 30 min. Se usa en:
  - ningún micrófono recibe sonido;
  - todas las IA fallan;
  - permiso de Google perdido (en `vigilante_google`).

## Seguridad
- El receptor solo escucha en `127.0.0.1` y ngrok es la única puerta. Sin firma válida de Meta no
  pasa nada, y sin `WHATSAPP_APP_SECRET` el receptor no arranca.
- Solo se acepta tu número; todo lo demás se descarta sin responder.
- Lo delicado requiere un «sí» decidido por el código. La herramienta de envío no acepta
  destinatarios.
- El contenido de correos, archivos, Drive y web sigue llegando envuelto en `<contenido_no_fiable>`,
  y el bloqueo de encargos de `tareas.py` sigue vigente.
- Las claves solo están en `.env`. `whatsapp_estado.json` y `whatsapp_recordatorios.json` van al
  `.gitignore`. El registro nunca guarda el texto de los mensajes.

## Errores y diagnóstico
- Cualquier fallo de WhatsApp o ngrok se anota y Jarvis sigue funcionando por voz.
- `diagnostico.py` comprueba:
  - que las variables están puestas (sin mostrar las claves);
  - que el token es válido (`GET /{PHONE_ID}`);
  - que `ngrok.exe` existe y que el dominio responde;
  - que la plantilla `aviso_jarvis` existe y está aprobada.

## Pruebas (`pruebas_unidad.py`, sin red)
- Firma válida aceptada; firma inválida o ausente rechazada con 403.
- Verificación del webhook con el token correcto e incorrecto.
- Mensaje de otro número ignorado; mensaje repetido procesado una sola vez; límite por minuto.
- Ventana de 24 h: texto libre dentro y plantilla fuera; reintento con plantilla si Meta rechaza.
- Partir textos largos y convertir `**negrita**`.
- Herramientas filtradas: la IA de WhatsApp no ve `abrir_programa`.
- Confirmación: «sí» ejecuta, «no» cancela, otro mensaje cancela y se procesa, y caduca a los 5 min.
- `encargar_tarea` desde WhatsApp pasa por la confirmación de `tareas.py`.
- Avisos de citas: uno por evento, sin repetir tras reiniciar y sin eventos de día completo.
- Recordatorios: guardar, enviar a su hora y enviar con retraso tras reiniciar.
- `aviso_grave` limitado a uno cada 30 min.

Prueba real manual, al final: mensaje de ida y vuelta, aviso con plantilla, confirmación de un correo
de prueba a ti mismo y recordatorio a 2 min.

## Lo que tiene que hacer el usuario (guía paso a paso en `LEEME.md`)
Esto requiere iniciar sesión y aceptar condiciones, así que no lo hace Jarvis:
1. Crear una app de tipo Business en developers.facebook.com y añadir el producto WhatsApp.
2. Añadir tu número como destinatario verificado del número de prueba.
3. Crear un usuario del sistema en Meta Business con permisos `whatsapp_business_messaging` y
   `whatsapp_business_management`, y generar su token permanente.
4. Crear la plantilla `aviso_jarvis` y esperar a que la aprueben.
5. Crear una cuenta en ngrok, instalar `ngrok.exe`, ejecutar `ngrok config add-authtoken …` y
   reservar el dominio fijo gratuito.
6. Rellenar las variables en `.env`, arrancar Jarvis y registrar el webhook en Meta con
   `https://<dominio>/whatsapp`, tu token de verificación y la suscripción al campo `messages`.

## Riesgos a comprobar al implementar
- Que el número de prueba de Meta permite usar plantillas propias aprobadas, además de `hello_world`.
  Si no, los avisos fuera de la ventana de 24 h quedan limitados hasta registrar un número real, y
  se documenta.
- La versión vigente de la Graph API y el formato exacto de la plantilla con parámetros.
- Que ngrok gratis no muestra su página de aviso a las peticiones de Meta (servidor a servidor no
  debería verla).

## Fuera de alcance
Notas de voz y fotos, varios usuarios, grupos, historial de mensajes recibidos con Jarvis apagado y
usar tu propio número como número de Jarvis.
