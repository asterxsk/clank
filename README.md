# clank

[![skills.sh](https://skills.sh/b/asterxsk/clank)](https://skills.sh/asterxsk/clank)

Computer use with inbuilt messages. Drive the desktop via the clank CLI (any harness, Windows/macOS/Linux). Background control plus sharp blue cursor, click tilt + ripple, typewriter reveal, and message pill with agent-chosen duration.

![clank demo](demo.svg)

## Layout

- `SKILL.md` — the skill: setup, actions, rules, overlay reference
- `clank.py` — harness CLI (one-shot + JSON-lines pipe) wrapping `cua-driver`
- `overlay.py` — Tk overlay: blue arrow cursor, click ripple, message pill, typewriter
- `kill_overlay.py` — kill stray overlay processes (Windows + macOS + Linux)

## Quick start

```sh
npx skills add asterxsk/clank
```

```sh
cua-driver --version          # install first if this fails, see SKILL.md
python3 clank.py apps
python3 clank.py pill --text hi --ms 2500
```

Full docs in `SKILL.md`.
