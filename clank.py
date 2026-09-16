#!/usr/bin/env python3
"""clank harness CLI — any agent harness drives the desktop through cua-driver.

File protocol (harness-agnostic): one JSON object per line on stdin, one per line on stdout.
  {"id": 1, "action": "apps"}
  {"id": 2, "action": "capture", "params": {"pid": 11312, "window_id": 525716}}
  {"id": 3, "action": "click", "params": {"pid": 11312, "x": 100, "y": 200}}
  {"id": 4, "action": "pill", "params": {"text": "opening repo", "ms": 2500}}

Actions: apps, windows, capture, shot, click, type, key, hotkey, launch, front,
  cursor (show/hide/move/state), pill (short message under cursor), sharp (small cursor on/off),
  busy (loading spinner while model thinks/responds).
Also usable as one-shot CLI:  python3 clank.py apps | capture --pid P --wid W | pill --text hi
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_DIR = Path(tempfile.gettempdir()) / "clank"
try:
    STATE_DIR.mkdir(exist_ok=True)
except OSError:
    STATE_DIR = HERE
STATE = STATE_DIR / "overlay-state.json"
CURSOR_COLOR = "#2563eb"  # blue — pill uses same color


def _driver_candidates():
    home = Path.home()
    cands = [os.environ.get("CUA_DRIVER_CMD", "").strip(), "cua-driver"]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local"
        cands += [str(Path(local) / "Programs" / "Cua" / "cua-driver" / "bin" / "cua-driver.exe"),
                  str(home / ".local" / "bin" / "cua-driver.exe")]
    elif sys.platform == "darwin":
        cands += [str(home / "Library" / "Cua" / "bin" / "cua-driver"),
                  str(home / ".local" / "bin" / "cua-driver"),
                  "/opt/homebrew/bin/cua-driver", "/usr/local/bin/cua-driver"]
    else:
        cands += [str(home / ".local" / "bin" / "cua-driver"),
                  str(home / ".local" / "share" / "cua" / "bin" / "cua-driver")]
    return [c for c in cands if c]


def find_driver() -> str:
    for c in _driver_candidates():
        hit = shutil.which(c)
        if hit:
            return hit
    if os.name == "nt":
        install = "irm https://cua.ai/driver/install.ps1 | iex"
    else:
        install = '/bin/bash -c "$(curl -fsSL https://cua.ai/driver/install.sh)"'
    raise RuntimeError(
        "cua-driver not found. Install it first: "
        + install
        + " (override: CUA_DRIVER_CMD=/path/to/cua-driver)")


def call(tool: str, **params):
    proc = subprocess.run([find_driver(), "call", tool, json.dumps(params or {})],
                           capture_output=True, text=True, timeout=120)
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out) if out else {"raw": out}
    except json.JSONDecodeError:
        return {"raw": out, "stderr": (proc.stderr or "")[-2000:], "returncode": proc.returncode}


def _stale_token(r):
    if not isinstance(r, dict):
        return False
    return "stale_element_token" in str(r.get("error", ""))


def write_state(**kv):
    cur = {}
    try:
        cur = json.loads(STATE.read_text())
    except (OSError, ValueError):
        pass
    cur.update(kv)
    STATE.write_text(json.dumps(cur))


def do(action: str, p: dict):
    if action == "apps":
        return call("list_apps")
    if action == "windows":
        return call("list_windows")
    if action == "capture":
        return call("get_window_state", pid=int(p.get("pid", 0)),
                    **({"window_id": int(p["window_id"])} if p.get("window_id") is not None else {}))
    if action == "shot":
        out = str(Path(p.get("out", STATE_DIR / "shot.png")).expanduser())
        r = call("get_desktop_state", screenshot_out_file=out)
        r["saved"] = out
        return r
    if action == "click":
        kw = {"pid": int(p.get("pid", 0))}
        if p.get("window_id") is not None:
            kw["window_id"] = int(p["window_id"])
        if p.get("element") is not None:
            kw["element_index"] = int(p["element"])
        elif p.get("token") is not None:
            kw["element_token"] = p["token"]
        else:
            kw.update({"x": int(p.get("x", 0)), "y": int(p.get("y", 0))})
        if p.get("mode"):
            kw["delivery_mode"] = p["mode"]
        # overlay sync: optional x/y (element frame center from last capture)
        # drives glide + ripple even on element/token clicks.
        if p.get("x") is not None:
            write_state(x=int(p["x"]), y=int(p["y"]),
                        click_x=int(p["x"]), click_y=int(p["y"]),
                        click_at=int(time.time() * 1000))
        r = call("click", **kw)
        if _stale_token(r) and (p.get("element") is not None or p.get("token") is not None):
            fresh = call("get_window_state", pid=int(p.get("pid", 0)),
                         **({"window_id": int(p["window_id"])} if p.get("window_id") is not None else {}))
            r["recaptured"] = isinstance(fresh, dict) and bool(fresh.get("elements"))
        return r
    if action == "type":
        kw = {"pid": int(p.get("pid", 0)), "text": p.get("text", "")}
        if p.get("window_id") is not None:
            kw["window_id"] = int(p["window_id"])
        if p.get("element") is not None:
            kw["element_index"] = int(p["element"])
        elif p.get("token") is not None:
            kw["element_token"] = p["token"]
        r = call("type_text", **kw)
        if _stale_token(r) and (p.get("element") is not None or p.get("token") is not None):
            fresh = call("get_window_state", pid=int(p.get("pid", 0)),
                         **({"window_id": int(p["window_id"])} if p.get("window_id") is not None else {}))
            r["recaptured"] = isinstance(fresh, dict) and bool(fresh.get("elements"))
        # feed overlay typewriter (100wpm, letter by letter)
        write_state(type_text=str(p.get("text", ""))[:120],
                    type_at=int(time.time() * 1000))
        return r
    if action == "key":
        return call("press_key", pid=int(p.get("pid", 0)), key=p.get("key", "Return"))
    if action == "hotkey":
        keys = p.get("keys", ["ctrl", "l"])
        if isinstance(keys, str):
            keys = keys.split("+")
        return call("hotkey", pid=int(p.get("pid", 0)), keys=keys)
    if action == "launch":
        return call("launch_app", path=p.get("path", ""), args=p.get("args", ""))
    if action == "front":
        return call("bring_to_front", pid=int(p.get("pid", 0)))
    if action == "cursor":
        sub = p.get("sub", "state")
        ses = {"session": p.get("session", "shared")}
        if sub == "show":
            return call("set_agent_cursor_enabled", enabled=True, **ses)
        if sub == "hide":
            return call("set_agent_cursor_enabled", enabled=False, **ses)
        if sub == "state":
            return call("get_agent_cursor_state", **ses)
        if sub == "move":
            write_state(x=int(p.get("x", 0)), y=int(p.get("y", 0)))
            return call("move_cursor", scope="window", x=int(p.get("x", 0)), y=int(p.get("y", 0)), **ses)
        raise ValueError(f"bad cursor sub: {sub}")
    if action == "pill":
        text = str(p.get("text", ""))[:120]
        ms = int(p.get("ms", 2500))
        write_state(pill=text, pill_ms=ms, color=CURSOR_COLOR)
        _ensure_overlay()
        return {"ok": True, "pill": text, "ms": ms, "color": CURSOR_COLOR}
    if action == "sharp":
        on = str(p.get("on", "on")).lower() in ("1", "on", "true", "yes")
        write_state(sharp=on, color=CURSOR_COLOR)
        if on:
            call("set_agent_cursor_enabled", enabled=False, session=p.get("session", "shared"))
        _ensure_overlay()
        return {"ok": True, "sharp": on}
    if action == "busy":
        on = str(p.get("on", "on")).lower() in ("1", "on", "true", "yes")
        write_state(busy=on)
        _ensure_overlay()
        return {"ok": True, "busy": on}
    raise ValueError(f"unknown action: {action}")


def _overlay_alive():
    try:
        return time.time() - os.path.getmtime(str(STATE) + ".alive") < 5
    except OSError:
        return False


def _ensure_overlay():
    """Start overlay GUI if not running (flag file heartbeat).
    Windows: pythonw (no console). POSIX: detached session.
    Single instance: skip spawn when heartbeat fresh."""
    if _overlay_alive():
        return
    ov = str(HERE / "overlay.py")
    if os.name == "nt":
        exe = sys.executable
        w = exe.replace("python.exe", "pythonw.exe")
        if os.path.exists(w):
            exe = w
        subprocess.Popen([exe, ov],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([sys.executable, ov],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def repl():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError as e:
            print(json.dumps({"id": None, "ok": False, "error": f"bad json: {e}"}), flush=True)
            continue
        rid = msg.get("id")
        try:
            res = do(msg.get("action", ""), msg.get("params", {}))
            print(json.dumps({"id": rid, "ok": True, "result": res}), flush=True)
        except Exception as e:  # harness must never hang
            print(json.dumps({"id": rid, "ok": False, "error": str(e)}), flush=True)


def one_shot(argv):
    a = argv[1]
    def opt(n, d=None):
        return argv[argv.index(f"--{n}") + 1] if f"--{n}" in argv else d
    if a == "apps":
        print(json.dumps(do("apps", {}), indent=1)[:3000])
    elif a == "windows":
        print(json.dumps(do("windows", {}), indent=1)[:3000])
    elif a == "capture":
        r = do("capture", {"pid": int(opt("pid", 0)), "window_id": opt("wid") and int(opt("wid"))})
        els = r.get("elements", []) if isinstance(r, dict) else []
        print(f"elements={len(els)}")
        for e in els[:20]:
            print(f"  [{e.get('element_index')}] {e.get('role')} '{str(e.get('label'))[:60]}'")
    elif a == "pill":
        print(do("pill", {"text": opt("text", "hi"), "ms": int(opt("ms", 2500))}))
    elif a == "click":
        print(json.dumps(do("click", {"pid": int(opt("pid", 0)), "window_id": opt("wid") and int(opt("wid")),
            "element": opt("element") and int(opt("element")), "token": opt("token"),
            "x": opt("x") and int(opt("x")), "y": opt("y") and int(opt("y")),
            "mode": opt("mode")}), indent=1)[:800])
    elif a == "type":
        print(json.dumps(do("type", {"pid": int(opt("pid", 0)), "window_id": opt("wid") and int(opt("wid")),
            "element": opt("element") and int(opt("element")), "token": opt("token"),
            "text": opt("text", "")}), indent=1)[:800])
    elif a == "key":
        print(json.dumps(do("key", {"pid": int(opt("pid", 0)), "key": opt("key", "Return")}), indent=1)[:500])
    elif a == "hotkey":
        print(json.dumps(do("hotkey", {"pid": int(opt("pid", 0)), "keys": opt("keys", "ctrl+l")}), indent=1)[:500])
    elif a == "launch":
        print(json.dumps(do("launch", {"path": opt("path", ""), "args": opt("args", "")}), indent=1)[:500])
    elif a == "front":
        print(json.dumps(do("front", {"pid": int(opt("pid", 0))}), indent=1)[:500])
    elif a == "shot":
        print(json.dumps(do("shot", {"out": opt("out", "shot.png")}), indent=1)[:800])
    elif a == "cursor":
        print(json.dumps(do("cursor", {"sub": opt("sub", "state"), "session": "shared"}), indent=1)[:1500])
    elif a == "sharp":
        print(do("sharp", {"on": opt("on", "on")}))
    elif a == "busy":
        print(do("busy", {"on": opt("on", "on")}))
    else:
        print(f"unknown: {a}. Try: apps windows capture shot click type key hotkey launch front pill cursor sharp busy")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        one_shot(sys.argv)
    else:
        repl()
