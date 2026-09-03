"""Use the modpack author's own server pack instead of guessing.

Deriving a server from a client instance means deciding, for every mod, whether
it belongs on a server - and nothing in a Forge jar reliably says. Every new
pack finds another way for that guess to be wrong.

Most published packs avoid the question entirely: the author builds and tests a
server pack, and CurseForge writes its file id into `minecraftinstance.json` at
install time. When that id is there, the guessing stops.

Packs without one (roughly two in five of those installed here) still fall back
to the derive-and-auto-heal path in sync.py and autoheal.py.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import CACHE_DIR, DATA_DIR
from .installer import download
from .instances import Instance

Log = Callable[[str], None]
Progress = Callable[[str, float], None]

# The website's own download route. api.curseforge.com needs a key; this does
# not, and redirects to the CDN.
DOWNLOAD_URL = "https://www.curseforge.com/api/v1/mods/{project}/files/{file}/download"

# Helper scripts and installers the pack ships for people setting a server up by
# hand. The launcher does all of this itself, and a stray start script that
# waits for a keypress is worse than no script at all.
SKIP_ROOT_NAMES = {
    "install.bat", "install.sh", "installer.bat", "installer.sh",
    "settings.bat", "settings.sh", "start.bat", "start.sh", "startserver.bat",
    "startserver.sh", "run.bat", "run.sh", "launch.bat", "launch.sh",
    "eula.txt", "server-icon.png",
}
SKIP_ROOT_SUFFIXES = (".txt", ".md", ".url", ".lnk")


@dataclass
class PackInfo:
    zip_path: Path
    file_id: int
    mods: int
    folders: list[str]


def _state_file(slug: str) -> Path:
    return DATA_DIR / f"serverpack-{slug}.json"


def installed_file_id(slug: str) -> int:
    try:
        return int(json.loads(_state_file(slug).read_text(encoding="utf-8"))["file_id"])
    except Exception:
        return 0


def _remember(slug: str, file_id: int, mods: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _state_file(slug).write_text(
        json.dumps({"file_id": file_id, "mods": mods}, indent=2), encoding="utf-8")


def forget(slug: str) -> None:
    _state_file(slug).unlink(missing_ok=True)


def needs_install(instance: Instance) -> bool:
    """True when a server pack exists and the extracted one is not it."""
    return (instance.has_server_pack
            and installed_file_id(instance.slug) != instance.server_pack_file_id)


def fetch(instance: Instance, progress: Progress | None = None) -> Path:
    url = DOWNLOAD_URL.format(project=instance.project_id,
                              file=instance.server_pack_file_id)
    dest = CACHE_DIR / f"serverpack-{instance.project_id}-{instance.server_pack_file_id}.zip"
    return download(url, dest, progress)


def _strip_prefix(names: list[str]) -> str:
    """Some packs wrap everything in one folder; others do not."""
    tops = {n.split("/")[0] for n in names if n.strip("/")}
    if len(tops) != 1:
        return ""
    only = tops.pop()
    # A single top-level *file* is not a wrapper folder.
    if any(n == only for n in names):
        return ""
    return only + "/"


def _skip(rel: str) -> bool:
    parts = rel.split("/")
    if len(parts) == 1:                       # only filter at the root
        low = parts[0].lower()
        return low in SKIP_ROOT_NAMES or low.endswith(SKIP_ROOT_SUFFIXES) \
            or ("installer" in low and low.endswith(".jar"))
    return False


def install(instance: Instance, server_dir: Path, zip_path: Path,
            log: Log | None = None) -> PackInfo:
    """Extract the server pack over server_dir, replacing mods wholesale.

    The author's mod list is the authority, so the old mods folder goes rather
    than being merged - a leftover jar from our own guessing would defeat the
    point of using their pack.
    """
    server_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("mods", "mods-disabled"):
        shutil.rmtree(server_dir / stale, ignore_errors=True)

    mods = 0
    folders: set[str] = set()
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        prefix = _strip_prefix(names)
        for entry in names:
            if entry.endswith("/"):
                continue
            rel = entry[len(prefix):] if prefix and entry.startswith(prefix) else entry
            if not rel or _skip(rel):
                continue
            target = server_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(entry) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            if rel.startswith("mods/") and rel.endswith(".jar"):
                mods += 1
            if "/" in rel:
                folders.add(rel.split("/")[0])

    _remember(instance.slug, instance.server_pack_file_id, mods)
    if log:
        log(f"ติดตั้ง server pack ทางการของ modpack แล้ว: ม็อด {mods} ตัว, "
            f"โฟลเดอร์ {', '.join(sorted(folders))}")
    return PackInfo(zip_path=zip_path, file_id=instance.server_pack_file_id,
                    mods=mods, folders=sorted(folders))


def cleanup_download(zip_path: Path) -> None:
    """Server packs run to hundreds of megabytes; keep none once extracted."""
    zip_path.unlink(missing_ok=True)
