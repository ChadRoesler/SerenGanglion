"""The .deb, read back the way dpkg reads it: an ar archive of debian-binary, control.tar.gz, data.tar.gz."""
from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_deb.py"
spec = importlib.util.spec_from_file_location("build_deb", TOOL)
build_deb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_deb)


def _wheel(folder: Path, name: str, files: dict[str, bytes], exe: tuple[str, ...] = ()) -> Path:
    path = folder / name
    with zipfile.ZipFile(path, "w") as z:
        for fname, data in files.items():
            info = zipfile.ZipInfo(fname)
            info.external_attr = (0o755 if fname in exe else 0o644) << 16
            z.writestr(info, data)
    return path


def _read_ar(raw: bytes) -> list[tuple[str, bytes]]:
    assert raw.startswith(b"!<arch>\n")
    i, out = 8, []
    while i < len(raw):
        head = raw[i:i + 60]
        assert head[58:60] == b"`\n"
        name, size = head[:16].decode().strip(), int(head[48:58])
        out.append((name, raw[i + 60:i + 60 + size]))
        i += 60 + size + (size % 2)
    return out


def _tar(data: bytes) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        return {m.name: (m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()}


@pytest.fixture
def wheels(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    _wheel(w, "seren_ganglion-0.2.0.dev3-py3-none-any.whl",
           {"seren_ganglion/__init__.py": b"UNIT = 'ganglion'\n", "seren_ganglion/__pycache__/x.pyc": b"junk"})
    _wheel(w, "seren_sinew-5.10.0-py3-none-any.whl", {"seren_sinew/__init__.py": b""})
    _wheel(w, "pyzmq-26.4.0-cp310-cp310-manylinux2014_aarch64.whl",
           {"zmq/__init__.py": b"", "pyzmq.libs/libzmq.so.5": b"\x7fELF"}, exe=("pyzmq.libs/libzmq.so.5",))
    return sorted(w.glob("*.whl"))


def test_the_deb_is_three_members_in_dpkgs_order(wheels, tmp_path):
    deb = build_deb.build(wheels, "0.2.0.dev3", tmp_path / "out", mtime=1_800_000_000)
    assert deb.name == "seren-ganglion_0.2.0~dev3_arm64.deb"
    members = _read_ar(deb.read_bytes())
    assert [n for n, _ in members] == ["debian-binary", "control.tar.gz", "data.tar.gz"]
    assert members[0][1] == b"2.0\n"


def test_control_says_what_it_is_and_what_it_carries(wheels, tmp_path):
    members = dict(_read_ar(build_deb.build(wheels, "0.2.0", tmp_path, mtime=1).read_bytes()))
    control = _tar(members["control.tar.gz"])["./control"][1].decode()
    assert "Package: seren-ganglion\n" in control and "Architecture: arm64\n" in control
    assert "Version: 0.2.0\n" in control and "Depends: python3 (>= 3.10)" in control
    assert "pyzmq 26.4.0" in control and "seren-sinew 5.10.0" in control
    ctl = _tar(members["control.tar.gz"])
    assert "./md5sums" in ctl
    for script in ("./postinst", "./prerm", "./postrm"):
        assert ctl[script][0].mode == 0o755 and ctl[script][1].startswith(b"#!/bin/sh\nset -e\n")
    assert b"systemctl enable seren-ganglion.service" in ctl["./postinst"][1]


def test_the_service_is_m5s_shape_plus_the_box(wheels, tmp_path):
    data = _tar(dict(_read_ar(build_deb.build(wheels, "0.2.0", tmp_path, mtime=1).read_bytes()))["data.tar.gz"])
    lines = data["./lib/systemd/system/seren-ganglion.service"][1].decode().splitlines()
    for line in ("Requires=llm-sys.service", "After=llm-sys.service", "Restart=always",
                 "ExecStart=/usr/bin/seren-ganglion run", "PrivateNetwork=yes", "RestrictAddressFamilies=AF_UNIX",
                 "CapabilityBoundingSet=", "ProtectSystem=strict", "NoNewPrivileges=yes", "ReadWritePaths=/tmp"):
        assert line in lines, line
    service = "\n".join(lines)
    assert "StartLimitIntervalSec=0" in service.split("[Service]")[0]   # in [Service] systemd ignores it
    assert "PrivateTmp" not in service   # the sockets live in /tmp


def test_the_files_land_under_opt_owned_by_root_with_no_bytecode(wheels, tmp_path):
    data = _tar(dict(_read_ar(build_deb.build(wheels, "0.2.0", tmp_path, mtime=1).read_bytes()))["data.tar.gz"])
    lib = "./opt/seren/ganglion/lib/"
    assert lib + "seren_ganglion/__init__.py" in data and lib + "seren_sinew/__init__.py" in data
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in data)
    assert all(m.uid == 0 and m.gid == 0 and m.uname == "root" for m, _ in data.values())
    wrapper, body = data["./usr/bin/seren-ganglion"]
    assert wrapper.mode == 0o755 and b"/usr/bin/python3 -I -c" in body and b"PYTHONPATH" not in body
    assert build_deb.launch_code("/opt/seren/ganglion/lib").encode() in body
    assert data[lib + "pyzmq.libs/libzmq.so.5"][0].mode == 0o755
    assert data[lib + "seren_ganglion/__init__.py"][0].mode == 0o644
    bundled = data["./opt/seren/ganglion/BUNDLED"][1].decode()
    assert bundled.count("sha256:") == 3 and "pyzmq 26.4.0" in bundled


def test_a_rebuild_with_the_same_inputs_is_byte_identical(wheels, tmp_path):
    a = build_deb.build(wheels, "0.2.0", tmp_path / "a", mtime=1_800_000_000).read_bytes()
    b = build_deb.build(wheels, "0.2.0", tmp_path / "b", mtime=1_800_000_000).read_bytes()
    assert a == b


def test_a_wheel_that_climbs_out_of_its_folder_is_refused(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    _wheel(w, "seren_ganglion-0.2.0-py3-none-any.whl", {"../../etc/passwd": b"x"})
    with pytest.raises(SystemExit, match="shouldn't"):
        build_deb.build(sorted(w.glob("*.whl")), "0.2.0", tmp_path / "out")


def test_no_ganglion_wheel_means_nothing_to_package(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    _wheel(w, "seren_sinew-5.10.0-py3-none-any.whl", {"seren_sinew/__init__.py": b""})
    with pytest.raises(SystemExit, match="nothing to package"):
        build_deb.build(sorted(w.glob("*.whl")), "0.2.0", tmp_path / "out")


@pytest.mark.parametrize("pep440,debian", [("0.2.0", "0.2.0"), ("0.2.0.dev3", "0.2.0~dev3"),
                                           ("0.2.0rc1", "0.2.0~rc1"), ("0.2.1.dev2+g1a2b3c", "0.2.1~dev2+g1a2b3c")])
def test_dev_versions_sort_before_their_release_in_debian_terms(pep440, debian):
    assert build_deb.debian_version(pep440) == debian


def _planted(folder: Path) -> Path:
    """A folder someone left a fake seren_ganglion and zmq in, the way /tmp might be on the module."""
    bad = folder / "seren_ganglion"
    bad.mkdir(parents=True)
    for name in ("__init__.py", "__main__.py"):
        (bad / name).write_text("print('PLANTED'); raise SystemExit(0)\n")
    (folder / "zmq.py").write_text("print('PLANTED')\n")
    return folder


def test_the_old_launch_ran_whatever_was_in_the_current_folder(tmp_path):
    """Proves the plant bites: `python -s -m`, the first wrapper, runs the fake (Psycheion, 21 Nov)."""
    out = subprocess.run([sys.executable, "-s", "-m", "seren_ganglion", "version"], cwd=_planted(tmp_path / "t"),
                         capture_output=True, text=True).stdout
    assert "PLANTED" in out


def test_the_wrappers_launch_runs_ours_from_a_folder_with_a_plant_in_it(tmp_path):
    real = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-I", "-c", build_deb.launch_code(str(real)), "version"],
                       cwd=_planted(tmp_path / "t"), capture_output=True, text=True,
                       env={"PYTHONPATH": str(tmp_path / "t"), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert r.returncode == 0, r.stderr
    assert "PLANTED" not in r.stdout and r.stdout.strip()
