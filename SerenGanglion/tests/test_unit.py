"""The unit end to end, on tcp: a fake sys hands out work ids, a PULL socket stands in for sys's line out
to the serial port, and requests arrive the way sys sends them (action, then the pair of push URL and JSON)."""
from __future__ import annotations

import json
import threading

import pytest

zmq = pytest.importorskip("zmq")

from seren_ganglion import unit, wire  # noqa: E402


class Bench:
    def __init__(self):
        self.ctx = zmq.Context()
        self.sys = self.ctx.socket(zmq.REP)
        sys_port = self.sys.bind_to_random_port("tcp://127.0.0.1")
        self.uart = self.ctx.socket(zmq.PULL)
        uart_port = self.uart.bind_to_random_port("tcp://127.0.0.1")
        self.uart_url = f"tcp://127.0.0.1:{uart_port}"
        self.sys_calls, self.next_number = [], 1001
        self._sys_stop = threading.Event()
        threading.Thread(target=self._serve_sys, daemon=True).start()

        probe = self.ctx.socket(zmq.REP)
        unit_port = probe.bind_to_random_port("tcp://127.0.0.1")
        probe.close()
        self.unit_url = f"tcp://127.0.0.1:{unit_port}"
        urls = {"sys": f"tcp://127.0.0.1:{sys_port}", "ganglion": self.unit_url}
        self.unit = unit.Unit(url_for=urls.__getitem__, context=self.ctx)
        ready = threading.Event()
        self.thread = threading.Thread(target=self.unit.serve, kwargs={"ready": ready}, daemon=True)
        self.thread.start()
        assert ready.wait(5)

    def _serve_sys(self):
        while not self._sys_stop.is_set():
            if not self.sys.poll(100):
                continue
            action, data = self.sys.recv_multipart()
            self.sys_calls.append((action.decode(), data.decode()))
            if action == b"register_unit":
                self.sys.send(wire.register_answer(self.next_number, "ipc:///o", "ipc:///i"))
                self.next_number += 1
            else:
                self.sys.send(b"None")

    def call(self, action: str, body: dict) -> tuple[bytes, dict]:
        req = self.ctx.socket(zmq.REQ)
        req.setsockopt(zmq.RCVTIMEO, 3000)
        req.connect(self.unit_url)
        req.send_multipart([action.encode(), wire.pack_pair(self.uart_url, json.dumps(body))])
        rpc = req.recv()
        req.close()
        line = self.uart.recv() if self.uart.poll(3000) else b""
        assert line.endswith(b"\n"), line   # one JSON line, as M5's units push it
        return rpc, json.loads(line)

    def close(self):
        self.unit.stop()
        self.thread.join(3)
        self._sys_stop.set()


@pytest.fixture
def bench():
    b = Bench()
    yield b
    b.close()


def test_setup_registers_with_sys_and_says_hello_down_the_serial_line(bench):
    rpc, line = bench.call("setup", {"request_id": "r1", "work_id": "ganglion", "action": "setup",
                                     "object": "ganglion.hello", "data": {}})
    assert rpc == b"None"                                   # the RPC answers None; the answer is pushed
    assert bench.sys_calls[0] == ("register_unit", "ganglion")
    assert line["request_id"] == "r1" and line["work_id"] == "ganglion.1001"
    assert line["object"] == "ganglion.hello" and line["error"] == {"code": 0, "message": ""}
    assert line["data"]["unit"] == "ganglion" and "held" in line["data"]["box"]
    assert set(line) == {"request_id", "work_id", "created", "object", "data", "error"}


def test_taskinfo_lists_tasks_and_the_box(bench):
    bench.call("setup", {"request_id": "r1", "object": "ganglion.hello"})
    _, line = bench.call("taskinfo", {"request_id": "r2", "work_id": "ganglion"})
    assert line["data"]["tasks"] == ["ganglion.1001"] and "box" in line["data"]
    _, one = bench.call("taskinfo", {"request_id": "r3", "work_id": "ganglion.1001"})
    assert one["data"]["work_id"] == "ganglion.1001" and one["data"]["object"] == "ganglion.hello"


def test_exit_gives_the_work_id_back_to_sys(bench):
    bench.call("setup", {"request_id": "r1"})
    _, line = bench.call("exit", {"request_id": "r2", "work_id": "ganglion.1001"})
    assert line["error"]["code"] == 0 and ("release_unit", "ganglion.1001") in bench.sys_calls
    _, again = bench.call("exit", {"request_id": "r3", "work_id": "ganglion.1001"})
    assert again["error"]["code"] == -101 and "no task" in again["error"]["message"]


def test_an_action_not_built_yet_answers_as_m5s_units_do(bench):
    _, line = bench.call("work", {"request_id": "r1", "work_id": "ganglion.1001"})
    assert line["error"] == {"code": -18, "message": "not have unit action!"}


def test_an_action_stackflow_doesnt_have_is_notaction(bench):
    req = bench.ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 3000)
    req.connect(bench.unit_url)
    req.send_multipart([b"bashexec", wire.pack_pair(bench.uart_url, "{}")])
    assert req.recv() == b"bashexec NotAction"
    req.close()


def test_garbage_doesnt_kill_the_unit(bench):
    req = bench.ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 3000)
    req.connect(bench.unit_url)
    req.send_multipart([b"setup", bytes([200]) + b"short"])   # a pair that lies about its length
    assert req.recv() == b"None"
    req.close()
    _, line = bench.call("setup", {"request_id": "after"})    # and it still answers
    assert line["request_id"] == "after"


def test_the_box_check_says_held_or_names_the_hole():
    box = unit.box_check()
    assert isinstance(box["held"], bool) and box["network_socket"]
