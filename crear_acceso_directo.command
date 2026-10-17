#!/bin/bash
# Crea un acceso a Jarvis en el Escritorio (equivalente a crear_acceso_directo.bat)
cd "$(dirname "$0")" || exit 1
DESTINO="$HOME/Desktop/Jarvis.command"
rm -f "$DESTINO"
cat > "$DESTINO" <<EOS
#!/bin/bash
exec "$PWD/jarvis.command"
EOS
chmod +x "$DESTINO"
echo "Acceso \"Jarvis\" creado en el escritorio."
sleep 3
