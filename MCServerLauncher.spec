# PyInstaller build recipe.
#
# The tkdnd Tcl extension is loaded by Tk at runtime from a folder on disk, so
# it has to be shipped as data rather than imported - PyInstaller cannot see it
# by analysing imports.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT = Path(os.getcwd())

datas = [
    (str(PROJECT / "assets" / "icon.ico"), "assets"),
    (str(PROJECT / "README.md"), "."),
]
manual = PROJECT / "docs" / "คู่มือการใช้งาน.docx"
if manual.is_file():
    datas.append((str(manual), "."))

# tkinterdnd2 ships per-platform Tcl libraries; take them all from vendor/.
vendor = PROJECT / "vendor"
if vendor.is_dir():
    for path in (vendor / "tkinterdnd2").rglob("*"):
        if path.is_file():
            datas.append((str(path), str(Path("tkinterdnd2") / path.parent.relative_to(vendor / "tkinterdnd2"))))

a = Analysis(
    ["MCServerLauncher.pyw"],
    pathex=[str(PROJECT), str(vendor)],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinterdnd2", "launcher", "launcher.session", "launcher.dnd"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PIL", "PyInstaller", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MC Server Launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,                 # a window app: no black console box
    icon=str(PROJECT / "assets" / "icon.ico"),
    version_info=None,
)
