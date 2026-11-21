"""The Sinew this package installs must import with nothing else around it, because on the module
it's copied in with --no-deps (no network to pip from). Released Sinew up to 5.9 imports starlette at
its front door and fails this; the lazy front door came with the release pinned in pyproject."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]

PROBE = textwrap.dedent("""
    import sys
    BLOCKED = ("starlette", "httpx", "anyio", "fastapi", "yaml", "pydantic")
    class Refuse:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError(f"{name} is not on the module")
    sys.meta_path.insert(0, Refuse())
    sys.path.insert(0, sys.argv[1])

    from seren_sinew.soma import Appendages
    from seren_sinew.cluster.dtos import from_dict
    import seren_ganglion.wire
    got = from_dict({"appendages": [{"name": "light", "ok": True, "provides": ["light"]}]}, Appendages)
    assert got.providing("light").name == "light", got
    loaded = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
    assert not loaded, loaded
    print("ok")
""")


def test_the_installed_sinew_imports_with_the_standard_library_alone():
    r = subprocess.run([sys.executable, "-I", "-c", PROBE, str(PKG_ROOT)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
