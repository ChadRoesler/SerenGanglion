"""StackFlow's wire between units on the module, spelled in Python. Standard library only.

Read from M5's source (m5stack/StackFlow, ext_components/StackFlow/stackflow), 20 Nov 2026:

- Every unit serves RPC on a ZeroMQ REP socket at ``ipc:///tmp/rpc.<unit>`` (pzmq.hpp,
  ``rpc_url_head_``). A call is two frames, the action's name then its data; the answer is one
  frame. An action the unit doesn't have answers ``"<action> NotAction"``.
- Two values travel as one string (``pzmq_data::set_param``): one byte holding the first value's
  length, then the first value, then the second.
- A unit joins by calling ``sys``'s ``register_unit`` with its name (StackFlow.cpp,
  ``sys_register_unit``). The answer is nested: the work id number, paired with a second pair of
  the unit's output URL and its inference URL.
- Setup reaches a unit as ``setup`` with the pair (the URL to push results to, the request's raw JSON).

Still to check against the live module: the socket files under /tmp (``ls -la /tmp/rpc.*``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

RPC_URL = "ipc:///tmp/rpc.{unit}"
Text = Union[str, bytes]


def _b(v: Text) -> bytes:
    return v.encode("utf-8") if isinstance(v, str) else bytes(v)


def pack_pair(first: Text, second: Text) -> bytes:
    """set_param: a length byte, the first value, the second. The first is at most 255 bytes
    (the length is one char; on the module's aarch64 a char is unsigned)."""
    a = _b(first)
    if len(a) > 255:
        raise ValueError(f"the first value of a pair is at most 255 bytes, not {len(a)}")
    return bytes([len(a)]) + a + _b(second)


def unpack_pair(raw: bytes) -> tuple[bytes, bytes]:
    """get_param(0) and get_param(1) of one message."""
    if not raw:
        raise ValueError("an empty message is not a pair")
    n = raw[0]
    if 1 + n > len(raw):
        raise ValueError(f"the pair says its first value is {n} bytes, and only {len(raw) - 1} follow")
    return raw[1:1 + n], raw[1 + n:]


def rpc_url(unit: str) -> str:
    return RPC_URL.format(unit=unit)


def work_id(unit: str, number: int) -> str:
    """How the core names one instance of a unit: "ganglion.1001"."""
    return f"{unit}.{number}"


@dataclass(frozen=True)
class Registration:
    """sys's answer to register_unit."""
    number: int        # the work id number
    out_url: str       # where this unit publishes its results
    inference_url: str


def register_answer(number: int, out_url: str, inference_url: str) -> bytes:
    """What sys sends back from register_unit: (number, (out_url, inference_url))."""
    return pack_pair(str(number), pack_pair(out_url, inference_url))


def parse_register_answer(raw: bytes) -> Registration:
    number, ports = unpack_pair(raw)
    out_url, inference_url = unpack_pair(ports)
    try:
        n = int(number.decode("ascii"))
    except ValueError:
        raise ValueError(f"register_unit answered a work id that isn't a number: {number!r}") from None
    return Registration(n, out_url.decode("utf-8"), inference_url.decode("utf-8"))
