# SerenGanglion

**Seren's reflexes on the M5Stack LLM module.** A ganglion is a cluster of nerve cells outside the
brain that runs reflexes without asking it, and a wake word is a reflex. Sibling to Sinew, Meninges,
Soma and Psycheion.

Status, 20 Nov 2026: **design, plus the StackFlow wire.** `seren_ganglion.wire` speaks the framing
M5's units use between themselves, and `sys_client` registers with `sys`; both are tested against a
fake `sys`. Nothing has run on a module yet.

## Where it runs

The LLM module (AX630C) is its own computer inside the StackChan: Ubuntu 22.04 (arm64), kernel 4.19,
about 1 GB of RAM, 32 GB of eMMC, M5's StackFlow units, and **no network of its own**. It talks to the
CoreS3 over one UART (JSON per line, up to 1.5 Mbaud). What's known about the module, and how it was
found, is in SerenSoma's `firmware/docs/appendages.md` under "The LLM module as ears".


Chad, 20 Nov: yes. A ganglion is a cluster of nerve cells outside the brain that runs reflexes without
asking it, and a wake word is a reflex. It sits beside Sinew, Meninges, Soma and Psycheion.

**A package, not a distro.** Forking M5's image means its Windows-only reflash with the module out of
the stack for every mistake, and owning a kernel 4.19 BSP with closed NPU blobs through every M5
update. Everything we want lives above the kernel. So it is **one `.deb`, `seren-ganglion`, installed
beside M5's StackFlow packages**, and `apt` treats it like theirs.

**It is a StackFlow unit** (`work_id: "ganglion"`), so it speaks StackFlow's JSON-per-line to the core
like every other unit, and the core's locked `llm` route needs only one more name on its list.
`bashexec`, `push`, `upgrade` and `rmmode` stay off the robot's API, as now.

What it does:

- **Listening, wired inside the module.** Wake word, VAD and Whisper chained on the module; the core
  gets one finished event (`heard`, with its text and timing). Only text crosses the UART.
- **Face sounds.** Plays the MP3s the core forwards (Psycheion's forward-on-play; `audio.play` takes
  wav, mp3 or pcm, not Opus), about 64 KB a line at most.
- **The three LEDs, its health, its versions.**
- **Its own upkeep:** the update Chad's module needed on 19 Nov as a script anyone can run, telnet on
  port 23 switched off at install, and a refusal to run on a StackFlow older than the one tested.

**Its shapes live in Sinew** beside the robot's, with the same contract test, so the two ends can't
drift. Sinew can run on the module: its floor is Python 3.10 and Ubuntu 22.04's is 3.10, so that floor
becomes a promise (a line in Sinew's README). Two things first:

- Check the module's Python really is 3.10 (one command over `adb`).
- `import seren_sinew` must need only the standard library. Today the package's front door pulls in
  starlette for the request-logging middleware (Psycheion, 20 Nov); load that only when asked, and the
  ganglion carries one small pure-Python wheel.

## The mic light is the core's, never the ganglion's

Psycheion, 20 Nov; Chad: "yes yes yes". A unit that crashes or hangs could leave a mic open and never
say so, which is the hidden microphone again. So:

1. **The ganglion opens a mic only when the core tells it to.** Never on its own, and never by itself
   after a restart.
2. **The core doesn't take its word for it.** Every few seconds it asks `sys.lstask`; if anything that
   captures audio is running (ours, or M5's `audio`, `kws`, `vad`, `asr`, `whisper`), the light is on.
3. **No answer counts as listening.** A module that stops replying keeps the light on until it answers.

The ganglion's own "mic open" event is still wanted, for the face's listening look, because it's fast.
It never decides the light.

## Connections: however the person brings it

Chad, 20 Nov: the module has a microSD slot and a USB-C port, and the Ethernet board "doesn't really go
on for the real stuff". So nothing assumes a network.

- **Talking to the robot is always the UART through the core.** It's the one link every StackChan with
  a module has. The ganglion listens on no network port.
- **Getting software and models on takes any of:**

  | Way | How |
  |---|---|
  | microSD | A folder of `.deb`s and models on the card; the installer finds it |
  | USB-C | `adb push` from a computer, or the installer run from that computer |
  | Ethernet, if someone has it | `apt` from M5's repo as usual |
  | The UART | Small things only; 1 MB is about 10 s at 1.5 Mbaud, base64 included |

  Whichever way, the installer checks the same checksums before it installs anything.

## Open

- Whether a StackFlow unit can be a Python process or has to be C++ on their framework. StackFlow's
  own units are C++; how ours registers with `sys` decides what the package is written in.
- Whether the microSD slot mounts in its Linux at all, and where.
- Whether its USB-C can be a network to a computer (a USB gadget), separate from `adb`. Untested; the
  19 Nov `adb reverse` was refused, and that's a different mechanism.

## Layout

| Where | What |
|---|---|
| `SerenGanglion/seren_ganglion/wire.py` | StackFlow's framing: pairs, `register_unit`'s answer, unit URLs. Standard library only |
| `SerenGanglion/seren_ganglion/sys_client.py` | RPC to `sys` or any unit over ZeroMQ (`pyzmq`, imported only here) |
| Sinew, `seren_sinew.ganglion` (to come) | The shapes the ganglion and the core exchange, contract-tested like the robot's |
| SerenSoma | The core's half: forwarding to `ganglion`, the `lstask` check behind the mic light, the allow list |

To come here: the unit itself (serve `setup`, `work`, `exit`), the `.deb` (`debian/`), and the
installer that takes microSD, USB-C, Ethernet or the UART.

## Tests

```
cd SerenGanglion
pip install -e ".[test]"   # the lean shape: as close to the module as a runner gets
python -m pytest
```

`[dev]` adds `pyzmq` for the socket tests, which run against a fake `sys` on tcp because Windows has
no ipc sockets. Python 3.10 is the floor because it's the module's.
