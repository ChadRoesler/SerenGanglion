"""Build seren-ganglion_<version>_arm64.deb from wheels. Standard library only, so it runs the same
on a desktop and in CI, with no dpkg-deb needed.

Everything inside is pure Python or an already-built wheel (pyzmq for manylinux2014_aarch64, cp310),
so the package is assembled here rather than compiled: each wheel is unpacked under
/opt/seren/ganglion/lib, a wrapper goes in /usr/bin, and BUNDLED records exactly what went in.

    python tools/build_deb.py --wheels ganglion-wheels --version 0.2.0 --out dist

A .deb is an ar archive of three members, in this order: debian-binary, control.tar.gz, data.tar.gz.

No systemd unit yet: it waits for `seren-ganglion run`, and for the module's read-off (who the unit
runs as, and how M5 starts theirs). Shipping a service that can only fail would be worse than none.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import re
import tarfile
import time
import zipfile
from pathlib import Path

PACKAGE = "seren-ganglion"
ARCH = "arm64"
PREFIX = "opt/seren/ganglion"
MAINTAINER = "Chad Roesler <ChadRoesler@Me.com>"
LIB = f"/{PREFIX}/lib"


def launch_code(lib: str) -> str:
    """The one line the wrapper hands python3 -I -c: our lib first, put in from inside, so nothing in
    the caller's folder or environment can stand in for it."""
    return f'import sys; sys.path.insert(0, "{lib}"); from seren_ganglion.__main__ import main; sys.exit(main())'


# Psycheion, 21 Nov: `python3 -m` puts the current folder first on sys.path, so a seren_ganglion/ or
# zmq.py planted in /tmp ran in place of ours, as root over adb. -I adds no current folder, ignores
# PYTHON* variables and user site-packages (3.10 has no -P; -I covers it, checked on 3.8 the same night).
WRAPPER = f"""#!/bin/sh
# seren-ganglion: Seren's unit on the LLM module. Its Python lives in {LIB}, apart from the
# system's and from M5's. Isolated (-I): the folder you run it from never gets a say.
exec /usr/bin/python3 -I -c '{launch_code(LIB)}' "$@"
"""


def debian_version(v: str) -> str:
    """PEP 440 to Debian: a dev or pre-release sorts before the release, so '.dev3' becomes '~dev3'."""
    public, plus, local = v.partition("+")   # the local part (+g1a2b3c, a git hash) is left alone
    return re.sub(r"\.?(dev|a|b|rc)(\d+)", r"~\1\2", public) + plus + local


def control_text(version: str, bundled: list[tuple[str, str]], installed_kb: int) -> str:
    carries = ", ".join(name for name, _ in bundled)
    return (f"Package: {PACKAGE}\nVersion: {debian_version(version)}\nArchitecture: {ARCH}\n"
            f"Maintainer: {MAINTAINER}\nDepends: python3 (>= 3.10)\nInstalled-Size: {installed_kb}\n"
            "Section: misc\nPriority: optional\nHomepage: https://github.com/ChadRoesler/SerenGanglion\n"
            "Description: Seren's reflexes on the M5Stack LLM module\n"
            " A StackFlow unit beside M5's own: it listens, plays what it's handed and looks\n"
            " after itself, and tells the robot's core only what it needs. Needs no network.\n"
            f" Carries: {carries}.\n")


class _Tree:
    """Files for one tar, every one root-owned, with fixed times so a rebuild is byte-identical."""

    def __init__(self, mtime: int):
        self.mtime, self.files, self.dirs = mtime, {}, set()

    def add(self, path: str, data: bytes, mode: int = 0o644):
        path = path.strip("/")
        self.files[path] = (data, mode)
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            self.dirs.add("/".join(parts[:i]))

    def tar_gz(self) -> bytes:
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
            def info(name, mode, kind, size=0):
                ti = tarfile.TarInfo("./" + name if name else ".")
                ti.mode, ti.type, ti.size, ti.mtime = mode, kind, size, self.mtime
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = "root"
                return ti
            tar.addfile(info("", 0o755, tarfile.DIRTYPE))
            for d in sorted(self.dirs):
                tar.addfile(info(d, 0o755, tarfile.DIRTYPE))
            for name in sorted(self.files):
                data, mode = self.files[name]
                tar.addfile(info(name, mode, tarfile.REGTYPE, len(data)), io.BytesIO(data))
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode="wb", mtime=self.mtime) as gz:
            gz.write(raw.getvalue())
        return out.getvalue()


def _ar(members: list[tuple[str, bytes]], mtime: int) -> bytes:
    out = bytearray(b"!<arch>\n")
    for name, data in members:
        out += f"{name:<16}{mtime:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode("ascii")
        out += data
        if len(data) % 2:
            out += b"\n"
    return bytes(out)


def build(wheels: list[Path], version: str, out_dir: Path, mtime: int | None = None) -> Path:
    mtime = int(time.time()) if mtime is None else mtime
    names = sorted(w.name for w in wheels)
    if not any(n.startswith("seren_ganglion-") for n in names):
        raise SystemExit("no seren_ganglion wheel among the wheels: nothing to package")
    data = _Tree(mtime)
    bundled = []
    for wheel in sorted(wheels, key=lambda w: w.name):
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        bundled.append((wheel.name.split("-")[0].replace("_", "-") + " " + wheel.name.split("-")[1], digest))
        with zipfile.ZipFile(wheel) as z:
            for item in z.infolist():
                if item.is_dir() or "__pycache__" in item.filename or item.filename.endswith(".pyc"):
                    continue
                if not re.fullmatch(r"[A-Za-z0-9_.+\-/]+", item.filename) or ".." in item.filename.split("/"):
                    raise SystemExit(f"{wheel.name} holds a path it shouldn't: {item.filename!r}")
                mode = (item.external_attr >> 16) & 0o777 or 0o644
                data.add(f"{PREFIX}/lib/{item.filename}", z.read(item), 0o755 if mode & 0o111 else 0o644)
    data.add(f"{PREFIX}/BUNDLED", "".join(f"{n}  sha256:{d}\n" for n, d in bundled).encode())
    data.add("usr/bin/seren-ganglion", WRAPPER.encode(), 0o755)

    installed_kb = max(1, sum(len(d) for d, _ in data.files.values()) // 1024)
    md5 = "".join(f"{hashlib.md5(d).hexdigest()}  {p}\n" for p, (d, _) in sorted(data.files.items()))
    control = _Tree(mtime)
    control.add("control", control_text(version, bundled, installed_kb).encode())
    control.add("md5sums", md5.encode())

    out_dir.mkdir(parents=True, exist_ok=True)
    deb = out_dir / f"{PACKAGE}_{debian_version(version)}_{ARCH}.deb"
    deb.write_bytes(_ar([("debian-binary", b"2.0\n"), ("control.tar.gz", control.tar_gz()),
                         ("data.tar.gz", data.tar_gz())], mtime))
    return deb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wheels", required=True, type=Path, help="a folder of the wheels to carry")
    ap.add_argument("--version", required=True, help="the package's version, as its tag gives it")
    ap.add_argument("--out", default=Path("dist"), type=Path)
    ap.add_argument("--mtime", type=int, default=None, help="file times, for a byte-identical rebuild")
    a = ap.parse_args(argv)
    deb = build(sorted(a.wheels.glob("*.whl")), a.version, a.out, a.mtime)
    print(f"{deb}  sha256:{hashlib.sha256(deb.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
