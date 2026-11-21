"""seren-ganglion <command>. Today: check (read-only), version."""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="seren-ganglion", description="Seren's unit on the LLM module.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="what this module is, read-only: versions, sockets, units, storage")
    sub.add_parser("version", help="this package's version")
    args = ap.parse_args(argv)
    if args.command == "check":
        from .check import main as check
        return check()
    from . import __version__
    print(__version__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
