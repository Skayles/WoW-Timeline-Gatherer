# -*- mode: python ; coding: utf-8 -*-
# Windows build: uv run pyinstaller wcl_notes.spec --noconfirm
# Output: "dist/WoW Timeline Gatherer/WoW Timeline Gatherer.exe" (one folder, fast start-up).
# Check a build: "WoW Timeline Gatherer.exe" --self-check report.json
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

APP_NAME = "WoW Timeline Gatherer"

# Files read at run time through importlib.resources.
datas = collect_data_files("wcl_notes", includes=["**/*.graphql", "**/*.yaml"])
# keyring finds its backends through package metadata.
datas += copy_metadata("keyring")

a = Analysis(
    ["packaging/launcher.py"],
    pathex=["src"],
    datas=datas,
    hiddenimports=["keyring.backends.Windows"],
    excludes=["tkinter", "pytest", "pytestqt", "mypy", "graphql", "PyInstaller"],
    noarchive=False,
)
# Software OpenGL fallback (20 MB): the timeline is drawn without OpenGL.
a.binaries = [b for b in a.binaries if not b[0].lower().endswith("opengl32sw.dll")]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)
