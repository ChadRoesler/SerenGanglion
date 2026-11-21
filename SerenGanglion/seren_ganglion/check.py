"""``seren-ganglion check``: what this module is, read-only. The adb read-off as a command.

Everything here only reads: versions, the C library, StackFlow's sockets and who may connect to
them, how M5 starts its units, and whether a microSD card shows up. It writes nothing and opens no
socket. Standard library only, and every part answers on its own, so one that fails says why and the
rest still report.
"""
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from typing import Any, Callable


def _part(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as e:  # a check that can't run says why; the rest still report
        return {"error": f"{type(e).__name__}: {e}"}


def python() -> dict:
    return {"version": platform.python_version(), "executable": sys.executable,
            "meets_floor": sys.version_info >= (3, 10)}


def libc() -> dict:
    name, version = platform.libc_ver()
    return {"name": name, "version": version, "machine": platform.machine()}


def packages() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    out: dict[str, Any] = {}
    for dist in ("seren-ganglion", "seren-sinew", "pyzmq"):
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            out[dist] = None
    try:
        import zmq
        out["libzmq"] = zmq.zmq_version()
    except Exception as e:
        out["libzmq"] = f"can't load: {type(e).__name__}: {e}"
    return out


def _who(path: str) -> dict:
    import grp, pwd  # POSIX only: the module is Linux, and a desktop running this reports the error
    st = os.stat(path)
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        owner = st.st_uid
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = st.st_gid
    mode = st.st_mode
    return {
        "path": path, "owner": owner, "group": group, "mode": stat.filemode(mode),
        "socket": stat.S_ISSOCK(mode),
        # connecting to a unix socket needs write permission on its file
        "group_may_connect": bool(mode & stat.S_IWGRP), "others_may_connect": bool(mode & stat.S_IWOTH),
        "i_may_connect": os.access(path, os.W_OK),
    }


def sockets() -> dict:
    import pwd
    found = sorted(glob.glob("/tmp/rpc.*")) + sorted(glob.glob("/tmp/llm/*"))
    return {"running_as": pwd.getpwuid(os.getuid()).pw_name, "sockets": [_who(p) for p in found]}


def units() -> Any:
    if not shutil.which("systemctl"):
        return {"error": "no systemctl"}
    r = subprocess.run(["systemctl", "list-units", "llm*", "--all", "--no-pager", "--plain", "--no-legend"],
                       capture_output=True, text=True, timeout=10)
    rows = [line.split(None, 4) for line in r.stdout.splitlines() if line.strip()]
    return [{"unit": x[0], "load": x[1], "active": x[2], "sub": x[3]} for x in rows if len(x) >= 4]


def storage() -> dict:
    with open("/proc/partitions", encoding="ascii") as f:
        parts = [line.split()[-1] for line in f.read().splitlines()[2:] if line.split()]
    with open("/proc/mounts", encoding="utf-8") as f:
        mounts = [line.split()[:3] for line in f if line.startswith("/dev/")]
    return {"block": [p for p in parts if p.startswith(("mmcblk", "sd"))],
            "mounted": [{"device": d, "on": m, "type": t} for d, m, t in mounts]}


CHECKS = {"python": python, "libc": libc, "packages": packages, "sockets": sockets, "units": units,
          "storage": storage}


def run() -> dict:
    return {name: _part(fn) for name, fn in CHECKS.items()}


def main() -> int:
    print(json.dumps(run(), indent=2, default=str))
    return 0
