@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Jarvis.lnk'); $s.TargetPath='%~dp0jarvis.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0ui\jarvis.ico'; $s.WindowStyle=7; $s.Save()"
echo Acceso directo "Jarvis" creado en el escritorio.
timeout /t 5 >nul
