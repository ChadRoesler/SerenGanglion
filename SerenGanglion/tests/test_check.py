"""seren-ganglion check: every part answers, or says why it couldn't, and nothing raises."""
import json
import subprocess
import sys

from seren_ganglion import check


def test_every_check_answers_or_says_why():
    got = check.run()
    assert set(got) == set(check.CHECKS)
    assert got["python"]["meets_floor"] is True
    json.dumps(got, default=str)   # printable whatever came back


def test_a_check_that_breaks_reports_instead_of_raising():
    assert check._part(lambda: 1 / 0) == {"error": "ZeroDivisionError: division by zero"}


def test_the_command_line_runs_check_and_version():
    out = subprocess.run([sys.executable, "-m", "seren_ganglion", "check"], capture_output=True, text=True, check=True)
    assert "python" in json.loads(out.stdout)
    v = subprocess.run([sys.executable, "-m", "seren_ganglion", "version"], capture_output=True, text=True, check=True)
    assert v.stdout.strip()
