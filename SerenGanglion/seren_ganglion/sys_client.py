"""Calling StackFlow's ``sys`` unit (or any unit's RPC) over ZeroMQ. Needs pyzmq, imported only here.

``url_for`` exists so tests can run a fake ``sys`` on tcp: there are no ipc sockets on Windows.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import wire


def call(unit: str, action: str, data: wire.Text = b"", *, timeout_ms: int = 3000,
         url_for: Callable[[str], str] = wire.rpc_url, context: Optional[object] = None) -> bytes:
    """One RPC: (action, data) in, one frame out. Raises TimeoutError when the unit doesn't answer."""
    import zmq

    ctx = context or zmq.Context.instance()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.LINGER, 0)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
    try:
        sock.connect(url_for(unit))
        sock.send(wire._b(action), zmq.SNDMORE)
        sock.send(wire._b(data))
        try:
            return sock.recv()
        except zmq.Again:
            raise TimeoutError(f"{unit} didn't answer {action} in {timeout_ms} ms") from None
    finally:
        sock.close()


def register(unit: str, **kw) -> wire.Registration:
    """Join StackFlow: sys hands back our work id number and our two URLs."""
    return wire.parse_register_answer(call("sys", "register_unit", unit, **kw))


def release(unit: str, number: int, **kw) -> bytes:
    return call("sys", "release_unit", wire.work_id(unit, number), **kw)
