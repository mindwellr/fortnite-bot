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

REPO = "mindwellr/fortnite-bot"
BRANCH = "main"
FILES = ("bot.py", "requirements.txt", "start.py")

# Se prueban varias direcciones de GitHub por si el hosting bloquea alguna
ZIP_URLS = (
    f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}",
    f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip",
    f"https://api.github.com/repos/{REPO}/zipball/{BRANCH}",
)
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{{name}}"

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)

def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "fortnite-bot-updater"})
    with urllib.request.urlopen(request, timeout=30) as resp:
        return resp.read()

def update_from_zip() -> bool:
    for url in ZIP_URLS:
        try:
            archive = zipfile.ZipFile(io.BytesIO(download(url)))
        except Exception as e:
            print(f"   {url} -> {e}")
            continue
        found = {}
        for entry in archive.namelist():
            # Dentro del zip los archivos están en "<carpeta>/<archivo>"
            name = entry.split("/", 1)[-1]
            if name in FILES:
                found[name] = archive.read(entry)
        if "bot.py" in found:
            for name, data in found.items():
                with open(name, "wb") as f:
                    f.write(data)
            return True
        print(f"   {url} -> bot.py not found in zip")
    return False

def update_from_raw() -> bool:
    downloaded = {}
    for name in FILES:
        url = RAW_URL.format(name=name)
        try:
            downloaded[name] = download(url)
        except Exception as e:
            print(f"   {url} -> {e}")
            return False
    for name, data in downloaded.items():
        with open(name, "wb") as f:
            f.write(data)
    return True

print("Downloading latest version from GitHub...")
if update_from_zip() or update_from_raw():
    print("Updated:", ", ".join(FILES))
else:
    print("⚠️ Could not update from GitHub. Starting with the current files.")

if not os.path.exists("bot.py"):
    sys.exit("❌ bot.py not found. Upload bot.py and requirements.txt manually from GitHub.")

print("Installing requirements...")
pip = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"]
if subprocess.call(pip + ["--user"]) != 0:
    subprocess.call(pip)

print("Starting bot...")
os.execv(sys.executable, [sys.executable, "bot.py"])
