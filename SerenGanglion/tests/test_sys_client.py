"""The sys client against a fake sys on tcp (ipc sockets don't exist on Windows)."""
import threading

import pytest

zmq = pytest.importorskip("zmq")

from seren_ganglion import sys_client, wire  # noqa: E402


def _fake_sys(answers):
    """A REP socket that answers each (action, data) from `answers`, and records what it got."""
    ctx = zmq.Context()
    rep = ctx.socket(zmq.REP)
    port = rep.bind_to_random_port("tcp://127.0.0.1")
    got = []

    def serve():
        for _ in range(len(answers)):
            action, data = rep.recv_multipart()
            got.append((action, data))
            fn = answers.get(action.decode())
            rep.send(fn(data) if fn else action + b" NotAction")
        rep.close()
        ctx.term()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return f"tcp://127.0.0.1:{port}", got, t


def test_register_asks_sys_by_our_name_and_reads_the_nested_answer():
    url, got, t = _fake_sys({"register_unit": lambda name: wire.register_answer(1001, "ipc:///o", "ipc:///i")})
    r = sys_client.register("ganglion", url_for=lambda unit: url)
    t.join(2)
    assert got == [(b"register_unit", b"ganglion")]
    assert r.number == 1001 and r.out_url == "ipc:///o" and r.inference_url == "ipc:///i"


def test_a_unit_that_never_answers_is_a_timeout_not_a_hang():
    ctx = zmq.Context()
    silent = ctx.socket(zmq.REP)
    port = silent.bind_to_random_port("tcp://127.0.0.1")
    try:
        with pytest.raises(TimeoutError):
            sys_client.call("sys", "lsmode", timeout_ms=200, url_for=lambda unit: f"tcp://127.0.0.1:{port}")
    finally:
        silent.close(linger=0)
        ctx.term()
