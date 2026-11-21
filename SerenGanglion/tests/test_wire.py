"""StackFlow's pair framing and register_unit's nested answer, as M5's C++ spells them."""
import subprocess
import sys

import pytest

from seren_ganglion import UNIT, wire


def test_a_pair_is_a_length_byte_then_both_values():
    raw = wire.pack_pair("ipc:///tmp/llm/ganglion.1001.sock", '{"request_id":"1"}')
    assert raw[0] == len("ipc:///tmp/llm/ganglion.1001.sock")
    assert wire.unpack_pair(raw) == (b"ipc:///tmp/llm/ganglion.1001.sock", b'{"request_id":"1"}')


def test_a_pair_can_have_empty_sides():
    assert wire.unpack_pair(wire.pack_pair("", "x")) == (b"", b"x")
    assert wire.unpack_pair(wire.pack_pair("x", "")) == (b"x", b"")


def test_a_first_value_over_255_bytes_is_refused_not_wrapped():
    with pytest.raises(ValueError):
        wire.pack_pair("a" * 256, "")
    assert wire.unpack_pair(wire.pack_pair("a" * 255, "b"))[0] == b"a" * 255   # the length byte is unsigned


def test_a_pair_that_lies_about_its_length_is_refused():
    with pytest.raises(ValueError):
        wire.unpack_pair(bytes([9]) + b"short")
    with pytest.raises(ValueError):
        wire.unpack_pair(b"")


def test_register_unit_answers_a_number_and_a_nested_pair_of_urls():
    raw = wire.register_answer(1001, "ipc:///tmp/llm/out.sock", "ipc:///tmp/llm/inference.sock")
    r = wire.parse_register_answer(raw)
    assert r == wire.Registration(1001, "ipc:///tmp/llm/out.sock", "ipc:///tmp/llm/inference.sock")
    assert wire.work_id(UNIT, r.number) == "ganglion.1001"
    assert wire.rpc_url("sys") == "ipc:///tmp/rpc.sys"


def test_register_unit_answering_nonsense_is_refused_plainly():
    with pytest.raises(ValueError, match="isn't a number"):
        wire.parse_register_answer(wire.pack_pair("nope", wire.pack_pair("a", "b")))


def test_the_wire_needs_nothing_but_the_standard_library():
    """The module has no network to pip from: importing the wire must load no third-party package."""
    code = ("import sys; import seren_ganglion.wire; "
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
            "{'zmq', 'starlette', 'httpx', 'anyio', 'fastapi', 'yaml', 'pydantic'}); print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
