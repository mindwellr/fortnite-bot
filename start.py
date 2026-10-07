"""
Arranque con actualización automática.

Cada vez que se enciende, descarga la última versión del bot desde GitHub
(rama main), instala las dependencias y arranca bot.py. Si GitHub no responde,
arranca con los archivos que ya tenga.

En el hosting solo hay que subir ESTE archivo (y crear el .env) y poner
start.py como archivo de inicio.
"""
import io
import os
import subprocess
import sys
import urllib.request
import zipfile

REPO_ZIP = "https://codeload.github.com/mindwellr/fortnite-bot/zip/refs/heads/main"
FILES = ("bot.py", "requirements.txt", "start.py")

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)

try:
    print("Downloading latest version from GitHub...")
    with urllib.request.urlopen(REPO_ZIP, timeout=30) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    for entry in archive.namelist():
        # Dentro del zip los archivos están en "fortnite-bot-main/<archivo>"
        name = entry.split("/", 1)[-1]
        if name in FILES:
            with open(name, "wb") as f:
                f.write(archive.read(entry))
    print("Updated:", ", ".join(FILES))
except Exception as e:
    print(f"⚠️ Could not update from GitHub ({e}). Starting with the current files.")

print("Installing requirements...")
pip = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"]
if subprocess.call(pip + ["--user"]) != 0:
    subprocess.call(pip)

print("Starting bot...")
os.execv(sys.executable, [sys.executable, "bot.py"])
