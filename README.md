# keystroke-recorder-win-py (input_recorder)

A Windows keyboard/mouse recorder in **Python** — a sibling of
[`keystroke-recorder-mac`](../keystroke-recorder-mac) and a modern port of the
C++ [`keystroke-recorder-win`](../keystroke-recorder-win). It captures low-level
keyboard or mouse input and writes it to JSON that can be replayed into, or used
to train, a behavioral-biometrics engine.

It keeps the **same CLI, output layout, filenames, and JSON schema** as the
macOS package, and mirrors the **Win32 semantics** of the original C++ tool
(VK-code key labels, `"<proc> exe -:- <title>"` window context, wheel deltas).

**This is a QA / data-collection tool** — a tester recording their own input (or
a controlled machine) to generate behavioral-biometrics signal data.

---

## Requirements

- Windows 10/11
- Python 3.9+
- [`pynput`](https://pypi.org/project/pynput/) and [`rich`](https://pypi.org/project/rich/)

**No special permission and no admin elevation** are required — Windows
low-level hooks (`WH_KEYBOARD_LL` / `WH_MOUSE_LL`) install in a normal
interactive session. The one caveat: to observe input directed at a window
running **as Administrator**, this process must also run elevated (a Windows
UIPI restriction, not a grantable permission).

## Install

```powershell
cd keystroke-recorder-win-py
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```
python -m input_recorder -d <data_dir> [options]
```

| Flag | Long form     | Required | Default      | Description                                          |
|------|---------------|----------|--------------|------------------------------------------------------|
| `-d` | `--data-dir`  | Yes      | —            | Output directory. Files go to `<dir>\KBD_JSON\` or `<dir>\MOUSE_JSON\` |
| `-u` | `--username`  | No       | Current user | Username prefix for filenames and `entity.user_id`   |
| `-r` | `--runtime`   | No       | 60           | Recording duration in seconds                        |
| `-i` | `--interval`  | No       | 60           | File flush interval in seconds                       |
| `-t` | `--type`      | No       | keyboard     | Signal type: `keyboard` or `mouse`                   |
| `--machine-id` / `--tenant` / `--tuid` | — | No | `FAKE_*` | Placeholder `entity.*` values |
| `--session-id` | —   | No       | generated UUID | Session id recorded in `metadata.session_id`       |
| `--task-type`  | —   | No       |   —          | Collection protocol: `free-text`, `fixed-text`, `free-mouse`, … |
| `--prompt-id`  | —   | No       |   —          | Identifier of the prompt/stimulus, if any            |
| `--backend`    | —   | No       | `auto`       | Capture backend: `auto`, `winhook`, or `pynput`      |
| `--plain`      | —   | No       |   —          | Plain reporter instead of the rich live TUI          |
| `--mask-keys`  | —   | No       |   —          | Hide typed characters in the live feed (`SimKey:•;<vk>`) |
| `--demo`       | —   | No       |   —          | Feed synthetic events (preview UI; no capture)       |

**Examples:**
```powershell
python -m input_recorder -d C:\Data -r 120 -i 30            # keyboard, 2 min
python -m input_recorder -d C:\Data -t mouse -r 300          # mouse, 5 min
python -m input_recorder -d C:\Data --demo                   # preview the TUI
```

Output filenames follow `<username><N>.json`, incrementing per flush. Press
**Ctrl+C** to stop early; the current buffer is flushed before exit.

## Capture backend (`--backend`)

| Backend | Timing source | Notes |
|---|---|---|
| `winhook` (default via `auto`) | **QPC sampled in the low-level hook** (`qpc_hook`) | CA-grade: a low-level hook fires synchronously with the event, so QueryPerformanceCounter is ≈ event time at sub-µs resolution — far finer than the ~15.6 ms `GetTickCount()` domain of the hook's own `time` field. Detects **auto-repeat**. Recommended. |
| `pynput` | callback time (`time.monotonic()`) | Portable fallback; `autorepeat` unknown. |

`--backend auto` (default) uses `winhook` and falls back to `pynput` if the hook
can't be installed.

## JSON schema

Schema `version: 2`, identical in shape to the macOS package (see
[DATA_COLLECTION.md](DATA_COLLECTION.md) for the field→feature mapping). Windows
specifics: key labels use **Windows VK codes** (alphanumerics → literal
lowercase/digit; everything else → `vk<code>`, e.g. space → `vk32`), and window
context is `"<proc> exe -:- <sanitized title>"`. Each keyboard payload entry ends
with `{"autorepeat": bool|null}` (`bool` from `winhook`, `null` from `pynput`).

## Console output

An interactive terminal shows a **rich live TUI** — header, time progress bar,
running stats, a recent-flush strip, and a scrolling event feed. `--plain` (or a
non-TTY / redirected output) falls back to a carriage-return status line plus
`✓ wrote …` log lines and a final summary (with a zero-event warning).

## Project layout

```
input_recorder/
├── __main__.py          # python -m input_recorder
├── app.py               # session driver / main loop  (≈ main.cpp)
├── cli_options.py       # argument parsing            (≈ cli_options.cpp)
├── entity_info.py       # entity block                (≈ entity_info.cpp)
├── window_context.py    # foreground proc/window (ctypes user32/kernel32)
├── keyboard_listener.py # pynput keyboard capture     (≈ keyboard_hook.cpp)
├── mouse_listener.py    # pynput mouse capture        (≈ mouse_hook.cpp)
├── winhook.py           # SetWindowsHookEx backend: QPC time + auto-repeat
├── displays.py          # EnumDisplayMonitors         (≈ EnumerateMonitors)
├── device_info.py       # device/screen/layout metadata
├── permissions.py       # no-op (Windows needs no permission)
├── reporting.py         # rich TUI + plain reporter
├── console.py           # low-level carriage-return line writer
├── demo.py              # synthetic event source for --demo
└── json_writer.py       # buffering + JSON output     (≈ json_writer.cpp)
```
