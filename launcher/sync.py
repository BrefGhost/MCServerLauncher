"""Mirror a client modpack instance into a server directory.

Mods are hard-linked rather than copied: a 1.6 GB pack costs a few kilobytes of
directory entries and syncs in under a second, and deleting a link never
touches the file CurseForge owns.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import DATA_DIR

Log = Callable[[str], None]

# Which top-level folders of an instance go to the server.
#
# This is a denylist, not an allowlist, and that is deliberate. Modpacks invent
# their own folder names - SkyFactory 5 keeps custom blocks in `thingpacks/`,
# which no allowlist would have contained - and a missing folder shows up as an
# unexplainable registry error rather than an obvious "file not found". Copying
# a folder the server ignores costs disk; missing one breaks the pack.
SKIP_TOP_DIRS = {
    # bulky client-only assets
    "resourcepacks", "shaderpacks", "screenshots", "packmenu",
    # caches, logs and launcher bookkeeping
    "logs", "crash-reports", "local", "downloads", "cache", "tv-cache",
    "changelogs", "server_pack", "overrides", "pregen", "profileimage",
    "dynamic-resource-pack-cache", "dynamic-data-pack-cache",
    # per-player client state, not pack content
    "saves", "backups", "essential", "fancymenu_data", "journeymap",
    "simple-rpc", "craftpresence", "observable_announce", "schematics", "esm",
}
# Folders whose names carry a version or date suffix, matched by prefix.
SKIP_TOP_PREFIXES = ("xaero", "optifine", "iris-reserve", "embeddium")
MODS_DIR = "mods"


def _skip_top(name: str) -> bool:
    """Is this top-level instance folder none of the server's business?"""
    low = name.lower()
    return (name == MODS_DIR
            or low.startswith(".")          # .mixin.out, .probe, .vscode, caches
            or low in SKIP_TOP_DIRS
            or low.startswith(SKIP_TOP_PREFIXES))


@dataclass
class SyncReport:
    linked: int = 0
    removed: int = 0
    autoheal_skipped: list[str] = field(default_factory=list)
    dirs_copied: list[str] = field(default_factory=list)

    @property
    def kept(self) -> int:
        return self.linked


def _state_file(slug: str) -> Path:
    return DATA_DIR / f"state-{slug}.json"


def load_state(slug: str) -> dict:
    p = _state_file(slug)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"disabled": {}, "config_synced": False}


def save_state(slug: str, state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _state_file(slug).write_text(json.dumps(state, indent=2, ensure_ascii=False),
                                 encoding="utf-8")


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def sync_mods(instance_dir: Path, server_dir: Path, slug: str,
              log: Log | None = None) -> SyncReport:
    """Put every mod from the instance on the server, minus what it rejected."""
    report = SyncReport()
    src_mods = instance_dir / "mods"
    dst_mods = server_dir / "mods"
    dst_mods.mkdir(parents=True, exist_ok=True)
    state = load_state(slug)
    disabled: dict = state.get("disabled", {})
    # Mods another mod turned out to depend on, so the client-side filter must
    # not throw them out again (GuideME under AE2 is the classic case).
    force_include: dict = state.get("force_include", {})

    wanted: dict[str, Path] = {}
    for jar in sorted(src_mods.glob("*.jar")):
        if jar.name in disabled:
            report.autoheal_skipped.append(jar.name)
            continue
        # Every mod goes on the server. Deciding up front which ones are
        # "client-side" needs a list of every mod ever written, and removing
        # one that the client keeps is what causes "mismatched mod channel
        # list" on join. The loader itself names the ones it cannot load, and
        # autoheal takes exactly those out - nothing else.
        wanted[jar.name] = jar

    for existing in list(dst_mods.glob("*.jar")):
        if existing.name not in wanted:
            existing.unlink(missing_ok=True)
            report.removed += 1

    for name, src in wanted.items():
        dst = dst_mods / name
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            report.linked += 1
            continue
        dst.unlink(missing_ok=True)
        _link_or_copy(src, dst)
        report.linked += 1

    if log:
        log(f"ใส่ม็อดลงเซิร์ฟเวอร์ครบทุกตัว: {report.linked} ตัว"
            + (f" (เว้น {len(report.autoheal_skipped)} ตัวที่เซิร์ฟเวอร์เคยปฏิเสธ)"
               if report.autoheal_skipped else ""))
    return report


def sync_content(instance_dir: Path, server_dir: Path, force: bool,
                 report: SyncReport, log: Log | None = None) -> None:
    """Copy config/scripts/datapacks. Existing server files win unless force."""
    for src in sorted(p for p in instance_dir.iterdir() if p.is_dir()):
        if _skip_top(src.name):
            continue
        copied = _copy_tree(src, server_dir / src.name, force)
        if copied:
            report.dirs_copied.append(f"{src.name} ({copied})")

    # Some packs ship a ready-made server.properties for their pack.
    default_props = instance_dir / "default-server.properties"
    target_props = server_dir / "server.properties"
    if default_props.is_file() and not target_props.exists():
        shutil.copy2(default_props, target_props)
        if log:
            log("ใช้ server.properties ที่มากับ modpack เป็นค่าตั้งต้น")

    if log and report.dirs_copied:
        log("คัดลอกโฟลเดอร์: " + ", ".join(report.dirs_copied))


def _copy_tree(src: Path, dst: Path, force: bool) -> int:
    """Copy a whole folder. Nothing is pruned inside it.

    Filtering by folder name at every depth used to drop real pack content:
    `global_packs/.../assets/forcecraft/patchouli_books/` and
    `config/defaultoptions/extra/journeymap/` are files the pack ships, not the
    client-only folders of the same name that sit at the instance root.
    """
    count = 0
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        out_dir = dst / rel
        for f in files:
            out = out_dir / f
            if out.exists() and not force:
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(Path(root) / f, out)
                count += 1
            except OSError:
                pass
    return count


def list_worlds(instance_dir: Path) -> list[str]:
    saves = instance_dir / "saves"
    if not saves.is_dir():
        return []
    return sorted(p.name for p in saves.iterdir()
                  if p.is_dir() and (p / "level.dat").exists())


def copy_world(instance_dir: Path, server_dir: Path, world_name: str,
               log: Log | None = None) -> None:
    """Copy a single-player save in as the server world (never overwrites)."""
    src = instance_dir / "saves" / world_name
    dst = server_dir / "world"
    if not src.is_dir():
        raise RuntimeError(f"ไม่พบโลก '{world_name}'")
    if dst.exists():
        raise RuntimeError("เซิร์ฟเวอร์นี้มีโลกอยู่แล้ว ลบโฟลเดอร์ world ก่อนถ้าจะทับ")
    if log:
        log(f"กำลังคัดลอกโลก '{world_name}' เข้าเซิร์ฟเวอร์ …")
    shutil.copytree(src, dst)
    if log:
        log("คัดลอกโลกเสร็จแล้ว")


def full_sync(instance_dir: Path, server_dir: Path, slug: str, force_config: bool,
              log: Log | None = None) -> SyncReport:
    state = load_state(slug)
    force = force_config or not state.get("config_synced")
    report = sync_mods(instance_dir, server_dir, slug, log)
    sync_content(instance_dir, server_dir, force and force_config, report, log)
    state["config_synced"] = True
    save_state(slug, state)
    return report
