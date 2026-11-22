# SerenGanglion

**Seren's reflexes on the M5Stack LLM module.**

A ganglion is a cluster of nerve cells outside the brain that runs reflexes without asking it, and a
wake word is a reflex. This one lives on the LLM module inside a StackChan: a StackFlow unit beside
M5's own, on the module's own Linux. It does the module's work there, and the robot's core hears only
what it needs. It sits in the Seren family beside
[Sinew](https://github.com/ChadRoesler/SerenSinew), Meninges, Soma and Psycheion.

## What's in it (today)

Early. The unit joins StackFlow and says hello; listening, sounds and LEDs come next.

- **`seren-ganglion check`:** what this module is, read-only. Its Python and C library, the versions it
  carries, StackFlow's sockets and **who may connect to them**, how M5 starts its units, and whether a
  microSD card shows up. Every part answers on its own, so one that can't run says why and the rest
  still report. It writes nothing and opens no socket.
- **The StackFlow wire** (`seren_ganglion.wire`): the framing M5's units use between themselves, read
  from M5's own C++ (`pzmq.hpp`, `StackFlow.cpp`), standard library only.
- **The `sys` client** (`seren_ganglion.sys_client`): registering with StackFlow's `sys` unit and calling
  any unit over ZeroMQ. It's the one part that needs pyzmq.
- **`seren-ganglion run`, the unit** (`seren_ganglion.unit`): it answers StackFlow's seven actions.
  `setup` registers a task with `sys` and pushes a `ganglion.hello` down the serial line to the core:
  its version, what it carries, and whether its box holds. `taskinfo` and `exit` work. `pause`, `work`,
  `link` and `unlink` answer -18, "not have unit action!", the way M5's own units do. Nothing in it
  opens a mic.
- **The `.deb`**, built on every release: one file with everything inside, for a module with no network,
  and `seren-ganglion.service`, enabled when it installs.

## Install

### On a module

Download `seren-ganglion_<version>_arm64.deb` from the
[releases](https://github.com/ChadRoesler/SerenGanglion/releases) and check it against that release's
`SHA256SUMS`. Get it onto the module however you have to hand (below), then:

```
dpkg -i seren-ganglion_<version>_arm64.deb
seren-ganglion check
```

The module needs no pip, no venv and no network. Everything is under `/opt/seren/ganglion/`, and
`dpkg -r seren-ganglion` takes it all away again.

### For working on it

```
pip install seren-ganglion
```

That gives you the Python package on a desktop, for development and tests. To fetch the wheels for a
module by hand: Ganglion and Sinew are pure Python, but pyzmq has to be fetched for the module's
platform. It comes as one file,
`pyzmq-26.4.0-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`, with ZeroMQ's library
inside:

```
pip download seren-ganglion seren-sinew --no-deps -d ganglion-wheels
pip download pyzmq --only-binary=:all: --platform manylinux2014_aarch64 --python-version 3.10 --no-deps -d ganglion-wheels
```

`--no-deps` because Sinew's declared dependencies (starlette and its family) are never imported here.
On the module a wheel is a zip, and `python3 -m zipfile -e <wheel> <folder>` needs nothing that isn't
already there.

## Where it runs

The LLM module (AX630C) is its own computer inside the StackChan: Ubuntu 22.04 (arm64), kernel 4.19,
about 1 GB of RAM, 32 GB of eMMC, M5's StackFlow units, and **no network of its own**. It talks to the
CoreS3 over one UART, as JSON lines at up to 1.5 Mbaud. What's known about the module, and how it was
found, is in SerenSoma's `firmware/docs/appendages.md`, under "The LLM module as ears".

**A package, not a distro.** Forking M5's image would mean their Windows-only reflash, with the module
out of the stack, for every mistake, and owning a kernel 4.19 BSP with closed NPU blobs through every
M5 update. Everything we want lives above the kernel, so it's one `.deb` beside M5's packages.

**Python 3.10 is the floor because it's the module's.** Raise it and the module falls off.

## What it will do

It joins StackFlow as the unit `ganglion`, so the core reaches it as `ganglion.<n>` through the same
locked route it uses for M5's units: one more name on that route's allow list. `bashexec`, `push`,
`upgrade` and `rmmode` stay off the robot's API.

- **Listening, wired inside the module.** Wake word, VAD and Whisper chained on the module. The core
  gets one finished event, `heard`, with its text and timing. Only text crosses the UART.
- **Face sounds.** It plays the MP3s the core forwards. M5's `audio.play` takes wav, mp3 or pcm, not
  Opus, so Psycheion's Face Studio makes the MP3s; at most about 64 KB a line.
- **The three LEDs, its health, its versions.**
- **Its own upkeep:** updating M5's StackFlow as a script anyone can run, telnet on port 23 switched off
  at install, and a refusal to run on a StackFlow older than the one tested.

**Its shapes live in Sinew**, beside the robot's, with the same contract test, so the two ends can't
drift. Sinew's body shapes import with the standard library alone from 5.10 on, and
`tests/test_sinew_on_the_module.py` holds us to it: it fails on 5.9, which imports starlette at its
front door.

**It can be Python.** StackFlow units talk ZeroMQ over socket files, and the protocol doesn't care
what a unit is written in (Psycheion read `pzmq.hpp` and `StackFlow.cpp`, 20 Nov; checked the same
night):

- Each unit answers requests on a REP socket at `ipc:///tmp/rpc.<unit>`. A call is two frames, the
  action then its data, and the answer is one frame.
- Two values travel as one string: a byte giving the first one's length, the first, then the second.
- A unit joins by calling `sys`'s `register_unit` with its name. The answer is nested: its work id
  number, paired with a second pair of its output URL and its inference URL.

## The mic light is the core's, never the ganglion's

Psycheion, 20 Nov; Chad: "yes yes yes". A unit that crashes or hangs could leave a mic open and never
say so, which is the hidden microphone again. So:

1. **The ganglion opens a mic only when the core tells it to.** Never on its own, and never by itself
   after a restart.
2. **The core doesn't take its word for it.** Every few seconds it asks `sys.lstask`. If a task that
   captures audio is set up (ours, or M5's `audio`, `kws`, `vad`, `asr` or `whisper`), the light is on.
   **Tasks, not services** (Psycheion, 21 Nov): all five of M5's listening services run all day as
   daemons waiting for a `setup`, so "the service is up" would keep the light on forever and mean
   nothing. Never build this against `systemctl`.
3. **No answer counts as listening.** A module that stops replying keeps the light on until it answers.

The ganglion's own "mic open" event is still wanted, for the face's listening look, because it's fast.
It never decides the light.

**The bench test for the rule is the kernel's own word.** ALSA shows whether a capture stream is
actually open, whoever opened it. The module has one capture device, and with nothing set up it reads
`closed` (Chad's module, 21 Nov):

```
cat /proc/asound/card0/pcm0c/sub0/status
```

On the bench the light must be on exactly while that says `RUNNING`.

## Connections: however the person brings it

Chad, 20 Nov: the module has a microSD slot and a USB-C port, and the Ethernet board "doesn't really go
on for the real stuff". So nothing assumes a network.

- **Talking to the robot is always the UART, through the core.** It's the one link every StackChan with
  a module has. The ganglion listens on no network port.
- **Getting the `.deb` and models on** takes whichever of these is to hand:

  | Way | How |
  |---|---|
  | microSD | Copy it onto the card. Unproven: on 21 Nov no card was in, so whether the slot shows up in its Linux is still open |
  | USB-C | `adb push` from a computer |
  | Ethernet, if someone has it | Download it on the module |
  | The UART | Later, through Soma (below). About ten seconds for the `.deb` |

## Who it runs as

Psycheion, 21 Nov: the ganglion parses whatever the core sends, so a parsing bug as root is a root bug,
on the box we locked `bashexec` away from. M5's units run as root, and their sockets may admit only root.
Connecting to a unix socket needs write permission on its file, which `check` reports.

**Answered by `check` on Chad's module, 21 Nov (v0.3.0): root-only.** Every StackFlow socket
(`/tmp/rpc.sys` and one per unit, plus `/tmp/llm/5556.sock`) is `root:root`, `srwxr-xr-x`: no group or
other may connect. M5 starts each unit as its own systemd service, `llm-<unit>.service`.

- **Had the sockets let a group write,** the `.deb` would make a `ganglion` system user in that group.
  They don't, so:
- **It runs as root, boxed by systemd**, and this section says so until it's fixed:

  ```
  NoNewPrivileges=yes
  CapabilityBoundingSet=
  ProtectSystem=strict
  ReadWritePaths=/var/lib/seren-ganglion /tmp
  ProtectHome=yes
  PrivateNetwork=yes
  RestrictAddressFamilies=AF_UNIX
  ```

  That means no capabilities, a read-only system apart from its own state and the sockets, and no
  network at all. Path-based unix sockets still work across a private network namespace, so StackFlow
  is reachable and nothing else is. `PrivateTmp` stays off, because the sockets live in `/tmp`. These
  need checking against the module's systemd before they're trusted.
- **We don't change M5's units** to loosen their sockets. A drop-in that changed how their root
  processes create files would reach well past ours.

**The service follows M5's own** (`systemctl cat llm-sys llm-skel`, 21 Nov): theirs run as root from
`/opt/m5stack`, `Restart=always`, `RestartSec=1`, `StartLimitInterval=0`, and every unit but `sys` has
`After=` and `Requires=llm-sys.service`. Ours, `seren-ganglion.service`, does the same, plus the box
above. The module's systemd is 249, built with `+SECCOMP`, and the kernel has seccomp (the `Seccomp:`
line in `/proc/self/status` only exists when it does).

**The unit tests its own box when it starts.** Whether the kernel has seccomp *filters*, which
`RestrictAddressFamilies` needs, doesn't show from outside. So the first thing it does is try to open
a network socket: under the box that fails. If it succeeds, the box has a hole, and the unit says so
in its log and in `taskinfo` rather than carrying on quietly. `PrivateNetwork=yes` still holds the
line by itself: a network socket in a private namespace reaches nothing but its own loopback.

**The kernel has everything the box needs** (`/proc/config.gz`, 21 Nov): `CONFIG_SECCOMP_FILTER=y`
and `CONFIG_NET_NS=y`. The self-test stays anyway, for the day a module ships a kernel without them.
On the NUC's systemd, a process under `RestrictAddressFamilies=AF_UNIX` got "Address family not
supported by protocol" for a network socket and opened a unix one, which is what the self-test reads.

**The service ships in the `.deb`** and is enabled on install: `lib/systemd/system/seren-ganglion.service`.
`StartLimitIntervalSec=0` sits in `[Unit]`, where systemd reads it; in `[Service]` it's ignored
(`systemd-analyze verify` caught it). M5 writes the older `StartLimitInterval`, which `[Service]` still
takes.

## Later: Soma installs it for you

Soma already fetches firmware from GitHub releases and checks checksums before staging it. It could
fetch this `.deb` the same way and send it to the module through the core. Psycheion, 21 Nov:
installing a `.deb` is `dpkg -i` as root, so while that install mode is on, whoever holds the robot's
token has root on the module. A checksum on the NUC proves the right file left the NUC, not who's
sending it now. So, before anyone builds the convenient version:

- **The switch is hands on the robot**, not the token: for example, holding the head for five seconds
  in the first two minutes after a boot. Soma's page says "touch the robot to allow the install".
- **It closes after one install or ten minutes**, whichever comes first.
- **It takes one file to one fixed path and runs one fixed command**, `dpkg -i` on that path. The core
  builds the command itself; nothing the caller sends ends up in it. It never takes shell lines.

## Releasing

The family's shape (`.github/workflows/release.yml`):

1. **Every push:** the tests, on Python 3.10 to 3.14. The first set is the leanest, Sinew and pytest
   only, as close to the module as a runner gets; `[dev]` adds pyzmq for the socket tests.
2. **A `vX.Y.Z` tag on `main`:** setuptools_scm takes the version from the tag, so the wheel and the
   `.deb` always carry the same number.
3. **The wheel and sdist** are built, then **the `.deb`** by `tools/build_deb.py`. That's pure Python,
   so it builds the same on a desktop as in CI, with no dpkg needed. Everything inside is pure Python
   or an already-built wheel, so there's nothing to compile for ARM. It carries the wheel just built,
   the newest Sinew the pyproject allows, and pyzmq for the module, and records each with its checksum
   in `/opt/seren/ganglion/BUNDLED`. File times come from the tagged commit, so a rebuild is
   byte-identical.
4. **The GitHub release** gets the wheel, the sdist, the `.deb` and `SHA256SUMS`. **PyPI** gets the
   wheel and sdist, by trusted publishing, so no token is stored.

A dev version like `0.2.0.dev3` becomes `0.2.0~dev3` in the `.deb`, so dpkg sorts it before `0.2.0`.

## Layout

| Where | What |
|---|---|
| `seren_ganglion/check.py` | `seren-ganglion check`, read-only |
| `seren_ganglion/unit.py` | `seren-ganglion run`: the StackFlow unit |
| `seren_ganglion/wire.py` | StackFlow's framing. Standard library only |
| `seren_ganglion/sys_client.py` | RPC to `sys` or any unit over ZeroMQ |
| `tools/build_deb.py` | The `.deb`, from wheels |
| Sinew, `seren_sinew.ganglion` (to come) | The shapes the ganglion and the core exchange |
| SerenSoma | The core's half: forwarding to `ganglion`, the `lstask` check behind the mic light, the allow list |

## Tests

```
cd SerenGanglion
pip install -e ".[test]"
python -m pytest
```

The socket tests run against a fake `sys` on tcp, because Windows has no ipc sockets. The `.deb` is read
back the way dpkg reads it, and a real one was checked with dpkg-deb on 21 Nov.

## What's coming

1. ~~`check` on a real module~~ done 21 Nov: Python 3.10.12, glibc 2.35, libzmq 4.3.5 loads, sockets root-only, units as `llm-<unit>.service`, systemd 249, the mic `closed` at rest.
2. ~~The unit joins StackFlow~~ built for 0.4: registers, says hello, `taskinfo`, `exit`. Next is
   `ganglion.hello` reaching Soma through the core for real, then listening.
3. ~~A systemd unit~~ ships in 0.4. Still to do: telnet off on install, once we know what serves port 23.
4. **Its shapes in Sinew**, and the core's half in Soma.

AGPL-3.0-or-later.
