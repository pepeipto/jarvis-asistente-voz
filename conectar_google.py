"""Conecta Jarvis con tu cuenta de Google (una sola vez) y comprueba que funciona.
Solo guarda recuentos en google/estado.txt (nunca el contenido de tus correos o eventos)."""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import google_conector as g  # noqa: E402


def main():
    g.DIR.mkdir(exist_ok=True)
    salida = g.DIR / "estado.txt"
    if not g.CRED.exists():
        msg = "FALTA google/credentials.json: primero hay que crear las credenciales en Google Cloud."
        print(msg)
        salida.write_text(msg + "\n", encoding="utf-8")
        return
    print("Se va a abrir el navegador. Elige tu cuenta de Google y pulsa Continuar / Permitir.")
    print("(Si sale 'Google no ha verificado esta aplicacion': pulsa Continuar. La app es tuya.)")
    try:
        g.autorizar()
    except Exception as e:
        salida.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} FALLO al autorizar: {e}\n", encoding="utf-8")
        print("FALLO:", e)
        return
    lineas = [f"{time.strftime('%Y-%m-%d %H:%M:%S')} Autorizado OK"]
    try:
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ev = g._servicio("calendar").events().list(
            calendarId="primary", timeMin=hoy.astimezone().isoformat(),
            timeMax=(hoy + timedelta(days=7)).astimezone().isoformat(), singleEvents=True).execute()
        lineas.append(f"Calendario OK: {len(ev.get('items', []))} eventos en los proximos 7 dias")
    except Exception as e:
        lineas.append(f"Calendario FALLO: {str(e)[:200]}")
    try:
        r = g._servicio("gmail").users().messages().list(userId="me", q="in:inbox is:unread", maxResults=1).execute()
        lineas.append(f"Gmail OK: unos {r.get('resultSizeEstimate', 0)} correos sin leer en la bandeja de entrada")
    except Exception as e:
        lineas.append(f"Gmail FALLO: {str(e)[:200]}")
    try:
        r = g._servicio("drive").files().list(q="trashed = false", pageSize=5, fields="files(id)").execute()
        lineas.append(f"Drive OK: acceso a tus archivos ({len(r.get('files', []))} recientes leidos)")
    except Exception as e:
        lineas.append(f"Drive FALLO: {str(e)[:200]}")
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))


main()
