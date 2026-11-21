"""seren_ganglion - Seren's reflexes on the M5Stack LLM module.

A ganglion is a cluster of nerve cells outside the brain that runs reflexes without asking it.
This is ours: a StackFlow unit on the module's own Linux (AX630C, Ubuntu 22.04, Python 3.10, no
network of its own), beside M5's units. It listens (wake word, VAD, speech-to-text chained on the
module, so only text crosses the UART), plays what it's handed, and looks after itself. The core
talks to it over the UART; it listens on no network port. See README.md.

Lean on purpose: the standard library, Sinew's stdlib-only shapes, and ZeroMQ only where a socket
is opened. Nothing here may need the network to install.
"""
from __future__ import annotations

try:  # the setuptools-scm build artifact (gitignored); present in installed wheels
    from ._version import version as __version__
except Exception:  # source checkout without a build -> metadata, then dev fallback
    try:
        from importlib.metadata import version as _v

        __version__ = _v("seren-ganglion")
    except Exception:
        __version__ = "0.0.0.dev0"

UNIT = "ganglion"   # our StackFlow unit name: the core reaches us as work_id "ganglion.<n>"
