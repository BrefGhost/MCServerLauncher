"""Download and install a Forge / NeoForge dedicated server."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

from .config import CACHE_DIR, FORGE_INSTALLER_URL, NEOFORGE_INSTALLER_URL

Progress = Callable[[str, float], None]  # message, 0..1 (-1 = indeterminate)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
UA = {"User-Agent": "MCServerLauncher/1.0 (+local tool)"}


def download(url: str, dest: Path, progress: Progress | None = None,
             sha256: str | None = None) -> Path:
    """Download to dest (atomically). Reuses an existing valid file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (sha256 is None or file_sha256(dest) == sha256):
        return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(f"กำลังดาวน์โหลด {dest.name}",
                         done / total if total else -1.0)

    if sha256 and file_sha256(tmp) != sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ไฟล์ที่ดาวน์โหลดมาไม่ตรงกับลายเซ็นที่คาดไว้: {url}")
    tmp.replace(dest)
    return dest


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def installer_url(loader: str, mc_version: str, loader_version: str) -> str:
    if loader == "neoforge":
        return NEOFORGE_INSTALLER_URL.format(ver=loader_version)
    if loader == "forge":
        return FORGE_INSTALLER_URL.format(mc=mc_version, ver=loader_version)
    raise RuntimeError(
        f"ยังไม่รองรับ mod loader ชนิด '{loader}' (รองรับ Forge และ NeoForge)")


def args_file(server_dir: Path, loader: str, mc_version: str,
              loader_version: str) -> Path | None:
    """The @argfile that Forge/NeoForge 1.17+ generates for the server."""
    if loader == "neoforge":
        p = server_dir / "libraries" / "net" / "neoforged" / "neoforge" / loader_version / "win_args.txt"
    else:
        p = server_dir / "libraries" / "net" / "minecraftforge" / "forge" / f"{mc_version}-{loader_version}" / "win_args.txt"
    if p.exists():
        return p
    # Fall back to whatever win_args.txt the installer left behind.
    found = list((server_dir / "libraries").rglob("win_args.txt"))
    return found[0] if found else None


def legacy_server_jar(server_dir: Path) -> Path | None:
    """Pre-1.17 Forge produced a runnable forge-*.jar instead of an argfile."""
    for pattern in ("forge-*.jar", "minecraft_server*.jar", "server.jar"):
        for j in server_dir.glob(pattern):
            if "installer" not in j.name:
                return j
    return None


def is_installed(server_dir: Path, loader: str, mc_version: str,
                 loader_version: str) -> bool:
    return bool(args_file(server_dir, loader, mc_version, loader_version)
                or legacy_server_jar(server_dir))


def install_server(server_dir: Path, java_exe: Path, loader: str, mc_version: str,
                   loader_version: str, progress: Progress | None = None,
                   log: Callable[[str], None] | None = None) -> None:
    """Run the official installer with --installServer into server_dir."""
    server_dir.mkdir(parents=True, exist_ok=True)
    url = installer_url(loader, mc_version, loader_version)
    jar = CACHE_DIR / Path(url).name

    if progress:
        progress(f"กำลังดาวน์โหลดตัวติดตั้ง {loader} {loader_version}", -1.0)
    download(url, jar, progress)

    if progress:
        progress(f"กำลังติดตั้งเซิร์ฟเวอร์ {loader} {loader_version} (ใช้เวลาสักครู่)", -1.0)

    proc = subprocess.Popen(
        [str(java_exe), "-jar", str(jar), "--installServer"],
        cwd=str(server_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    assert proc.stdout is not None
    for line in proc.stdout:
        if log:
            log(line.rstrip())
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ตัวติดตั้ง {loader} จบการทำงานด้วยรหัส {code}")

    if not is_installed(server_dir, loader, mc_version, loader_version):
        raise RuntimeError("ติดตั้งเสร็จแต่หาไฟล์สำหรับสั่งรันเซิร์ฟเวอร์ไม่เจอ")

    # The installer leaves a log and a copy of itself behind.
    for junk in server_dir.glob("*installer*.jar*"):
        junk.unlink(missing_ok=True)


def build_command(server_dir: Path, java_exe: Path, loader: str, mc_version: str,
                  loader_version: str, jvm_args: list[str]) -> list[str]:
    """Full command line to launch the installed server."""
    af = args_file(server_dir, loader, mc_version, loader_version)
    if af:
        rel = af.relative_to(server_dir).as_posix()
        return [str(java_exe), *jvm_args, f"@{rel}", "nogui"]
    jar = legacy_server_jar(server_dir)
    if jar:
        return [str(java_exe), *jvm_args, "-jar", jar.name, "nogui"]
    raise RuntimeError("ยังไม่ได้ติดตั้งเซิร์ฟเวอร์")


def uninstall(server_dir: Path) -> None:
    """Remove an installed server but keep worlds and configs."""
    for name in ("libraries", "run.bat", "run.sh", "user_jvm_args.txt"):
        target = server_dir / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
