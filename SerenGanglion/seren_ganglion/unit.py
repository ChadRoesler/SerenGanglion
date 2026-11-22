"""``seren-ganglion run``: the unit itself, a StackFlow unit called ``ganglion``.

What it is to StackFlow, from M5's ``StackFlow.cpp`` and ``StackFlow.h`` (read 21 Nov 2026):

- It answers RPC on a REP socket at ``ipc:///tmp/rpc.ganglion``. Each of the seven actions (setup,
  pause, work, exit, link, unlink, taskinfo) arrives as a pair: the URL to push the answer to, and the
  request's raw JSON. The RPC itself answers ``None``; the real answer is pushed.
- An answer is one JSON line, ``{"request_id", "work_id", "created", "object", "data", "error"}`` plus
  a newline, pushed to that URL. ``ipc:///tmp/llm/5556.sock`` is sys's line out to the serial port,
  so that is the core's ear.
- ``setup`` makes a task: the unit registers with sys, which hands back the task's work id number.
  ``exit`` gives it back. An action a unit hasn't got answers error -18, "not have unit action!", as
  M5's own units do.

What it does today: ``setup`` answers ``ganglion.hello`` with what it is and whether its box holds;
``taskinfo`` and ``exit`` work; the rest answer -18 until they're built. Nothing here opens a mic.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import UNIT, __version__, sys_client, wire

log = logging.getLogger("seren_ganglion")

NOT_BUILT = {"code": -18, "message": "not have unit action!"}   # M5's own words for it
# Ours, not M5's: their framework only ever answers -18. Kept apart from M5's numbers on purpose.
def no_task(work_id: str) -> dict:
    return {"code": -101, "message": f"ganglion has no task {work_id}"}

ACTIONS = ("setup", "pause", "work", "exit", "link", "unlink", "taskinfo")


def box_check() -> dict:
    """Whether the systemd box holds: under RestrictAddressFamilies=AF_UNIX a network socket can't be
    made. If one can, say so plainly; PrivateNetwork still leaves it nothing but its own loopback."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError as e:
        return {"held": True, "network_socket": f"refused: {e.strerror or e}"}
    s.close()
    return {"held": False, "network_socket": "opened: the address-family filter isn't on"}


def carries() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for dist in ("seren-ganglion", "seren-sinew", "pyzmq"):
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            out[dist] = None
    return out


@dataclass
class Task:
    work_id: str
    number: int
    object: str
    push_url: str
    request_id: str
    since: float = field(default_factory=time.time)


class Unit:
    """One ganglion. ``url_for`` and ``push`` are seams for the tests (tcp on Windows, a fake sys)."""

    def __init__(self, name: str = UNIT, *, url_for: Callable[[str], str] = wire.rpc_url,
                 push: Optional[Callable[[str, bytes], None]] = None, context: Any = None):
        import zmq
        self.zmq = zmq
        self.name, self.url_for = name, url_for
        self.ctx = context or zmq.Context.instance()
        self.push = push or self._push
        self.tasks: dict[str, Task] = {}
        self.box = box_check()
        self.started = time.time()
        self._stop = threading.Event()

    # ── the wire out ──

    def _push(self, url: str, line: bytes) -> None:
        sock = self.ctx.socket(self.zmq.PUSH)
        sock.setsockopt(self.zmq.LINGER, 1000)
        try:
            sock.connect(url)
            sock.send(line)
        finally:
            sock.close()

    def answer(self, url: str, request_id: str, work_id: str, obj: str, data: Any,
               error: Optional[dict] = None) -> None:
        body = {"request_id": request_id, "work_id": work_id, "created": int(time.time()), "object": obj,
                "data": data, "error": error or {"code": 0, "message": ""}}
        self.push(url, (json.dumps(body, separators=(",", ":")) + "\n").encode())

    # ── the actions ──

    def handle(self, action: str, data: bytes) -> bytes:
        """One RPC: the pair in, "None" back (the answer itself is pushed)."""
        if action not in ACTIONS:
            return f"{action} NotAction".encode()
        try:
            url_b, raw_b = wire.unpack_pair(data)
            url, raw = url_b.decode(), json.loads(raw_b.decode() or "{}")
        except (ValueError, UnicodeDecodeError) as e:
            log.warning("%s: a request that isn't a pair of url and JSON (%s)", action, e)
            return b"None"
        rid = str(raw.get("request_id", ""))
        wid = str(raw.get("work_id", self.name))
        getattr(self, "do_" + action, self.do_not_built)(url, rid, wid, raw)
        return b"None"

    def do_setup(self, url, rid, wid, raw):
        reg = sys_client.register(self.name, url_for=self.url_for, context=self.ctx)
        work_id = wire.work_id(self.name, reg.number)
        self.tasks[work_id] = Task(work_id, reg.number, str(raw.get("object", "")), url, rid)
        log.info("setup: %s (%s)", work_id, raw.get("object", ""))
        self.answer(url, rid, work_id, "ganglion.hello",
                    {"unit": self.name, "version": __version__, "carries": carries(), "box": self.box})

    def do_taskinfo(self, url, rid, wid, raw):
        if wid in self.tasks:
            t = self.tasks[wid]
            data: Any = {"work_id": t.work_id, "object": t.object, "since": int(t.since)}
        else:
            data = {"tasks": sorted(self.tasks), "box": self.box, "version": __version__,
                    "up_seconds": int(time.time() - self.started)}
        self.answer(url, rid, wid, "ganglion.taskinfo", data)

    def do_exit(self, url, rid, wid, raw):
        t = self.tasks.pop(wid, None)
        if t is None:
            self.answer(url, rid, wid, "None", "None", no_task(wid))
            return
        sys_client.release(self.name, t.number, url_for=self.url_for, context=self.ctx)
        log.info("exit: %s", wid)
        self.answer(url, rid, wid, "None", "None")

    def do_not_built(self, url, rid, wid, raw):
        self.answer(url, rid, wid, "None", "None", NOT_BUILT)

    # ── the loop ──

    def serve(self, *, bind: Optional[str] = None, ready: Optional[threading.Event] = None) -> None:
        rep = self.ctx.socket(self.zmq.REP)
        rep.setsockopt(self.zmq.LINGER, 0)
        rep.bind(bind or self.url_for(self.name))
        log.info("ganglion %s up on %s; box %s", __version__, bind or self.url_for(self.name),
                 "holds" if self.box["held"] else "HAS A HOLE: " + self.box["network_socket"])
        if ready:
            ready.set()
        try:
            while not self._stop.is_set():
                if not rep.poll(200):
                    continue
                frames = rep.recv_multipart()
                action = frames[0].decode(errors="replace")
                data = frames[1] if len(frames) > 1 else b""
                try:
                    reply = self.handle(action, data)
                except Exception:
                    log.exception("%s failed", action)
                    reply = b"None"
                rep.send(reply)
        finally:
            rep.close()
            for t in list(self.tasks.values()):   # give sys its work ids back on the way out
                try:
                    sys_client.release(self.name, t.number, url_for=self.url_for, context=self.ctx, timeout_ms=500)
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop.set()


def main() -> int:
    import signal
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    unit = Unit()
    signal.signal(signal.SIGTERM, lambda *_: unit.stop())
    try:
        unit.serve()
    except KeyboardInterrupt:
        pass
    return 0
