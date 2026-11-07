#!/usr/bin/env python3
"""Élague l'installation PySide6 d'un AppDir : ne garde que Core, Gui, Widgets, Svg et leurs dépendances.

Usage : prune.py <site-packages>
Les bibliothèques conservées sont déterminées par fermeture transitive des entrées ELF « NEEDED ».
"""
import shutil, subprocess, sys
from pathlib import Path

sp = Path(sys.argv[1])
ps, shib = sp / "PySide6", sp / "shiboken6"
qt = ps / "Qt"

ROOT_MODULES = ["QtCore", "QtGui", "QtWidgets", "QtSvg", "QtSvgWidgets"]
KEEP_PLUGINS = {
    "platforms": ["libqxcb.so", "libqwayland.so", "libqoffscreen.so", "libqminimal.so"],
    "imageformats": ["libqjpeg.so", "libqpng.so", "libqsvg.so", "libqgif.so"],
    "iconengines": ["libqsvgicon.so"],
    "platforminputcontexts": None, "platformthemes": ["libqxdgdesktopportal.so"],
    "wayland-decoration-client": None, "wayland-graphics-integration-client": None,
    "wayland-shell-integration": None, "xcbglintegrations": None,
}

def needed(path):
    out = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True).stdout
    return [l.split("[")[1].rstrip("]") for l in out.splitlines() if "(NEEDED)" in l and "[" in l]

search = [ps, qt / "lib", shib]
def find(name):
    for d in search:
        if (d / name).exists():
            return d / name

keep: set[Path] = set()
queue: list[Path] = []
def add(p):
    p = p.resolve() if p.is_symlink() else p
    if p not in keep:
        keep.add(p); queue.append(p)

for m in ROOT_MODULES:
    for f in ps.glob(f"{m}.abi3.so"): add(f)
for f in ps.glob("libpyside6.abi3.so*"): add(f)
for f in shib.glob("*.so*"): add(f)
for sub, names in KEEP_PLUGINS.items():
    d = qt / "plugins" / sub
    if d.is_dir():
        for f in d.glob("*.so"):
            if names is None or f.name in names: add(f)

while queue:
    p = queue.pop()
    for n in needed(p):
        t = find(n)
        if t: add(t)

keep_names = {p.name for p in keep}
# supprime tout fichier .so / .so.N non conservé (y compris les liens), sauf les plugins déjà filtrés
removed = 0
for f in list(sp.rglob("*.so*")):
    if f.is_dir(): continue
    target = f.resolve() if f.is_symlink() else f
    if target in keep or f.name in keep_names: continue
    if f.is_relative_to(ps) or f.is_relative_to(shib):
        f.unlink(); removed += 1

# dossiers et fichiers inutiles
drop = ["include", "scripts", "typesystems", "glue", "support", "examples", "designer", "assistant", "linguist",
        "lupdate", "lrelease", "qmlformat", "qmllint", "qmlls", "uic", "rcc", "svgtoqml", "balsam", "balsamui",
        "qtdiag", "qsb", "pyside6-*", "__pycache__"]
for pat in drop:
    for f in ps.glob(pat):
        shutil.rmtree(f) if f.is_dir() else f.unlink()
for sub in ("qml", "translations", "metatypes", "libexec", "lib/cmake", "modules", "resources", "doc"):
    t = qt / sub
    if t.exists(): shutil.rmtree(t)
for f in ps.glob("*.pyi"): f.unlink()
for f in ps.glob("*.json"): f.unlink()
for f in ps.glob("py.typed"): f.unlink()
# plugins : dossiers non retenus
if (qt / "plugins").is_dir():
    for d in (qt / "plugins").iterdir():
        if d.name not in KEEP_PLUGINS: shutil.rmtree(d)
# modules Python PySide6 non utilisés (les .so retirés ci-dessus)
for f in ps.glob("Qt*.abi3.so"):
    if f.name.split(".")[0] not in ROOT_MODULES: f.unlink()
# pip, setuptools, wheel : inutiles à l'exécution
for name in ("pip", "setuptools", "wheel", "pkg_resources", "_distutils_hack"):
    for f in sp.glob(name + "*"):
        shutil.rmtree(f) if f.is_dir() else f.unlink()
print(f"conservé : {len(keep)} bibliothèques, supprimé : {removed} fichiers .so")
