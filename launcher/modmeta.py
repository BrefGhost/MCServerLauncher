"""Read a mod jar's own description of itself.

This is only ever used to turn a name the loader printed ("reforgium",
"Wakes") back into the jar it came from. The launcher does not decide which
mods belong on a server - the server does that, and says so in its log.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TOML_FILES = ("META-INF/mods.toml", "META-INF/neoforge.mods.toml")

RE_SECTION = re.compile(r"^\s*(\[\[?[^\]]+\]\]?)")
RE_MODID = re.compile(r'^\s*modId\s*=\s*["\']([^"\']+)["\']')
RE_DISPLAY = re.compile(r'^\s*displayName\s*=\s*["\']([^"\']+)["\']')


@dataclass
class ModInfo:
    jar: Path
    mod_ids: list[str] = field(default_factory=list)
    display_name: str = ""


def _from_toml(text: str) -> tuple[list[str], str]:
    """Ids and display name a jar *provides*.

    Only `[[mods]]` counts: `[[dependencies.<modid>]]` blocks carry a `modId`
    key too, and reading those as provided ids makes every mod look like it
    ships its own dependencies.
    """
    ids: list[str] = []
    display = ""
    in_mods = False
    for line in text.splitlines():
        section = RE_SECTION.match(line)
        if section:
            in_mods = section.group(1).replace(" ", "") == "[[mods]]"
            continue
        if not in_mods:
            continue
        m = RE_MODID.match(line)
        if m:
            ids.append(m.group(1))
            continue
        m = RE_DISPLAY.match(line)
        if m and not display:
            display = m.group(1)
    return ids, display


def inspect(jar: Path) -> ModInfo:
    """Never raises - a jar we cannot parse simply has no metadata."""
    mod_ids: list[str] = []
    display = ""
    try:
        with zipfile.ZipFile(jar) as z:
            names = set(z.namelist())
            toml_name = next((t for t in TOML_FILES if t in names), None)
            if toml_name:
                mod_ids, display = _from_toml(
                    z.read(toml_name).decode("utf-8", "replace"))
            elif "fabric.mod.json" in names:
                data = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"))
                if data.get("id"):
                    mod_ids = [data["id"]]
                display = data.get("name", "") or ""
    except Exception:
        pass

    return ModInfo(jar=jar, mod_ids=mod_ids or [jar.stem.lower()],
                   display_name=display)
