---
name: clank
description: Computer use with inbuilt messages. Drive the desktop via the clank CLI (any harness, Windows/macOS/Linux). Background control plus sharp blue cursor, click tilt + ripple, typewriter reveal, and message pill with agent-chosen duration.
---

# clank — computer use with inbuilt messages

`clank.py` wraps the open-source `cua-driver` binary (`cua-driver call <tool>`),
a background engine using UIA (Windows), AX (macOS), AT-SPI
(Linux). `overlay.py` is a Tk overlay: blue arrow cursor,
click tilt + ripple, message pill, typewriter reveal.

Run from this skill's own directory. `python3` on macOS/Linux, `py -3` or
`python` on Windows.

## Setup — cua-driver (install if missing)

Check first — if this prints a version, skip to verify:

`cua-driver --version`

Install only when that fails.

Windows (PowerShell):

```powershell
irm https://cua.ai/driver/install.ps1 | iex
cua-driver autostart kick
```

Requires Windows 10/11 with an interactive desktop session. `autostart kick`
registers start-at-sign-in and starts the daemon now — no reboot.

macOS / Linux:

```sh
/bin/bash -c "$(curl -fsSL https://cua.ai/driver/install.sh)"
```

macOS requires 14 (Sonoma) or later. Then:

```sh
open -n -g -a CuaDriver --args serve
cua-driver permissions grant
```

Grant Accessibility + Screen Recording when prompted (the TCC grant sticks to
CuaDriver.app only when started via the app bundle).
Linux requires an x86_64 desktop session with X11 or XWayland plus AT-SPI 2.
Raw background input on Wayland has compositor-specific limits — prefer
X11/XWayland.

Verify:

```sh
cua-driver --version
cua-driver doctor
cua-driver call list_apps
```

Expect version output, a clean doctor, and an app-list JSON.

Where clank finds it (`clank.py` probes in order):

- `CUA_DRIVER_CMD` env override, then `cua-driver` on PATH
- Windows: `%LOCALAPPDATA%\Programs\Cua\cua-driver\bin\cua-driver.exe`,
  `~/.local/bin/cua-driver.exe`
- macOS: `~/Library/Cua/bin/cua-driver`, `~/.local/bin/cua-driver`,
  `/opt/homebrew/bin/cua-driver`, `/usr/local/bin/cua-driver`
- Linux: `~/.local/bin/cua-driver`, `~/.local/share/cua/bin/cua-driver`

Override example: `$env:CUA_DRIVER_CMD="C:\path\to\cua-driver.exe"` (PowerShell)
or `export CUA_DRIVER_CMD=/path/to/cua-driver` (sh).

Python check (3.10+, Tk, no extra deps):

```sh
python3 --version
python3 -c "import tkinter; print('tk ok')"
```

Windows: `py -3 --version` and `py -3 -c "import tkinter; print('tk ok')"`.

Troubleshooting:

- `cua-driver` not found after install → reopen the shell (stale PATH),
  then re-run `--version`.
- Windows daemon not running → re-run `cua-driver autostart kick` in an
  interactive session.
- macOS permission denied → re-run the daemon via
  `open -n -g -a CuaDriver --args serve`, then `cua-driver permissions grant`.
- Linux input fails on Wayland → switch to an X11/XWayland session,
  confirm AT-SPI 2 is installed.
- Still broken → `cua-driver check-update` / `cua-driver update --apply`,
  or re-run the installer over the top (manual fallback: releases at
  github.com/trycua/cua).

## Modes

One-shot: `python3 clank.py <cmd> [--flags]`
Pipe (JSON lines, any harness): stdin one object per line
`{"id":1,"action":"click","params":{"pid":P,"x":100,"y":200}}` →
stdout `{"id":1,"ok":true,"result":{...}}`. Errors keep the request `id`.
A parse failure answers `{"id":null,...}`.

## Actions (both modes, params in pipe `params`)

| Action | Params | Notes |
|---|---|---|
| `apps` | — | running + installed apps (pid, name, launch_path) |
| `windows` | — | top-level windows (pid, window_id, title, bounds) |
| `capture` | `pid`, `window_id?` | UIA/AX tree + `element_token` + frame per element |
| `shot` | `out?` | full desktop PNG, returns `saved` path |
| `click` | `pid`, `window_id?`, `element?`\|`token?`\|`x`+`y`, `mode?` | background default; `mode:"foreground"` only if driver refuses |
| `type` | `pid`, `window_id?`, `element?`\|`token?`, `text` | also feeds overlay typewriter |
| `key` | `pid`, `key` | e.g. `Return`, `Escape`, `Tab` |
| `hotkey` | `pid`, `keys` (`"ctrl+l"` or `["ctrl","l"]`) | XAML/UWP targets may refuse — use element click instead |
| `launch` | `path`, `args?` | hidden launch, no focus steal |
| `front` | `pid` | bring to foreground (visible — user sees it) |
| `cursor` | `sub: show\|hide\|state\|move`, `x?`, `y?`, `session?` | driver overlay control; `move` also glides clank cursor |
| `pill` | `text`, `ms?` | message pill, agent-chosen duration (default 2500) |
| `busy` | `on: on\|off` | spinner while model thinks/responds; off restores triangle |
| `sharp` | `on: on\|off` | hide bulky driver cursor, use clank arrow |

One-shot flags mirror params: `--pid --wid --element --token --x --y --text
--key --keys --path --args --out --sub --on --ms`.

## Rules that bite

- Coordinates are NATIVE desktop pixels = element `frame` space. Never scale.
- Capture fresh per `(pid, window_id)` before element/token actions. Tokens go
  stale after any re-render (`stale_element_token` → capture again, retry).
- Direct `cua-driver call` needs `element_token`, never bare index.
- Overlay glide/ripple on clicks: pass the element's frame center as `x,y`
  alongside `element`/`token` (driver ignores it, overlay uses it).
- Background first. Foreground only after a `background_unavailable` refusal.

## Overlay (`overlay.py`, pythonw — no console)

- Sharp blue arrow, eased glide toward state `{x,y}`.
- Click: 18° forward tilt + single blue ripple, 12→80px, 600ms fade.
- Pill: squircle, bottom-right of cursor, word-wrapped, max 200×300px,
  left-aligned, shadow-grounded. `pill --text T --ms N` shows T for N ms.
- Typing: letter-by-letter reveal at 100wpm + `▍` caret, holds 2s.
- State: OS temp dir (`.../clank/overlay-state.json`), never the install dir;
  heartbeat `.alive` (5s TTL).
  `clank.py` auto-starts the overlay when stale. Single instance only —
  extras exit at startup; idle overlay quits after 60s with no state writes.
  Kill strays with `python3 kill_overlay.py`.
- Transparency/color degrade gracefully off-Windows (font stack:
  Segoe UI → SF Pro → Helvetica Neue → DejaVu Sans).

## Requirements

See Setup above: `cua-driver` resolvable (PATH, standard location, or
`CUA_DRIVER_CMD`), Python 3.10+ with Tk, no extra deps.
