"""Locate a JVM with the right major version for a given Minecraft version.

Modpack players almost always already have the right JREs on disk because the
CurseForge / Mojang launchers ship them, so we look there before asking the
user to install anything.
"""
from __future__ import annotations

import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def required_major(mc_version: str) -> int:
    """Java major version Mojang targets for a given Minecraft version."""
    parts = re.findall(r"\d+", mc_version or "")
    nums = [int(p) for p in parts[:3]]
    while len(nums) < 3:
        nums.append(0)
    _, minor, patch = nums
    if minor >= 21:
        return 21
    if minor == 20:
        return 21 if patch >= 5 else 17   # 1.20.5+ moved to Java 21
    if minor >= 18:
        return 17
    if minor == 17:
        return 16
    return 8


def _candidate_paths() -> list[Path]:
    home = Path(os.path.expanduser("~"))
    appdata = Path(os.environ.get("APPDATA", ""))
    roots = [
        home / "curseforge" / "minecraft" / "Install" / "runtime",
        appdata / ".minecraft" / "runtime",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Java",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Eclipse Adoptium",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft" / "jdk",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Amazon Corretto",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Zulu",
    ]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        # java.exe sits at <root>/*/*/*/bin/java.exe for launcher runtimes and
        # at <root>/*/bin/java.exe for normal JDK installs.
        for depth in ("*/bin/java.exe", "*/*/bin/java.exe", "*/*/*/bin/java.exe"):
            found.extend(root.glob(depth))

    jhome = os.environ.get("JAVA_HOME")
    if jhome:
        found.append(Path(jhome) / "bin" / "java.exe")

    from shutil import which
    on_path = which("java")
    if on_path:
        found.append(Path(on_path))
    return found


@lru_cache(maxsize=256)
def java_major(exe: str) -> int:
    """Run `java -version` and return the major version, or 0 if unusable."""
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             timeout=20, creationflags=NO_WINDOW)
    except Exception:
        return 0
    text = (out.stderr or "") + (out.stdout or "")
    m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not m:
        return 0
    major = int(m.group(1))
    if major == 1:                       # "1.8.0_451" style
        major = int(m.group(2) or 0)
    return major


def find_java(mc_version: str) -> tuple[Path | None, int, str]:
    """Return (java.exe, major, note) for the given Minecraft version.

    Falls back to the newest JVM available if the exact major is missing, and
    says so in the note so the UI can warn the user.
    """
    want = required_major(mc_version)
    by_major: dict[int, Path] = {}
    for exe in _candidate_paths():
        if not exe.is_file():
            continue
        major = java_major(str(exe))
        if major and major not in by_major:
            by_major[major] = exe

    if want in by_major:
        return by_major[want], want, ""
    if not by_major:
        return None, 0, "ไม่พบ Java บนเครื่องเลย"

    # Prefer the closest version at or above what Minecraft wants.
    above = sorted(m for m in by_major if m > want)
    if above:
        m = above[0]
        return by_major[m], m, f"ไม่มี Java {want} ใช้ Java {m} แทน (อาจมีม็อดบางตัวไม่รองรับ)"
    m = max(by_major)
    return by_major[m], m, f"ต้องการ Java {want} แต่มีแค่ Java {m} — เซิร์ฟเวอร์อาจไม่สตาร์ท"
