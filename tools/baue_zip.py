"""Paket bauen:  python tools/baue_zip.py   ->  dist/kotor_import-<version>.zip

Ein ZIP fuer alle Blender-Versionen: Ordner kotor_import/ mit __init__.py (bl_info,
Blender 4.0/4.1: Preferences > Add-ons > Install) und blender_manifest.toml
(ab 4.2: Install from Disk, als Extension).
"""
import os
import re
import zipfile

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
PAKET = os.path.join(WURZEL, "kotor_import")


def version():
    t = open(os.path.join(PAKET, "blender_manifest.toml"), encoding="utf-8").read()
    v = re.search(r'^version\s*=\s*"([^"]+)"', t, re.M).group(1)
    init = open(os.path.join(PAKET, "__init__.py"), encoding="utf-8").read()
    bl = re.search(r'"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)', init).groups()
    sz = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(PAKET, "szene.py"), encoding="utf-8").read(), re.M).group(1)
    if ".".join(bl) != v or sz != v:
        raise SystemExit("Versionen passen nicht: manifest %s, bl_info %s, szene.py %s" % (v, ".".join(bl), sz))
    return v


def main():
    v = version()
    os.makedirs(os.path.join(WURZEL, "dist"), exist_ok=True)
    ziel = os.path.join(WURZEL, "dist", "kotor_import-%s.zip" % v)
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for ordner, dirs, dateien in os.walk(PAKET):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for d in sorted(dateien):
                if d.endswith((".pyc", ".pyo")):
                    continue
                pfad = os.path.join(ordner, d)
                z.write(pfad, os.path.relpath(pfad, WURZEL).replace("\\", "/"))
        z.write(os.path.join(WURZEL, "LICENSE"), "kotor_import/LICENSE")
    print(ziel)


if __name__ == "__main__":
    main()
