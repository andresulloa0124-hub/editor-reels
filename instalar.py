# Descarga la última versión del editor de Reels desde GitHub a /tmp/editor-reels.
# Lo ejecuta la skill al empezar cada chat. Solo usa la librería estándar de Python.
import json
import os
import urllib.request

REPO = "andresulloa0124-hub/editor-reels"
RAMA = "main"
BASE = f"https://raw.githubusercontent.com/{REPO}/{RAMA}/"
DESTINO = "/tmp/editor-reels"


def bajar(ruta):
    req = urllib.request.Request(BASE + ruta, headers={"User-Agent": "editor-reels", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


manifiesto = json.loads(bajar("manifest.json"))
for ruta in manifiesto["archivos"]:
    destino = os.path.join(DESTINO, ruta)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(bajar(ruta))
print(f"✅ Editor de Reels v{manifiesto['version']} listo en {DESTINO} ({len(manifiesto['archivos'])} archivos)")
print(f"   Guía: {DESTINO}/GUIA.md · Motor: {DESTINO}/motor/editor.py")
