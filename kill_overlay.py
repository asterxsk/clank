#!/usr/bin/env python3
"""Kill stray clank overlay processes (portable: Windows + macOS + Linux)."""
import os
import subprocess
import sys

PAT = "overlay.py"


def _win_cmdline(pid):
    for cmd in (["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/VALUE"],
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
            if PAT in out:
                return True
        except Exception:
            continue
    return False


def _win():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    cur = os.getpid()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() in ("python.exe", "pythonw.exe"):
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            if pid != cur and _win_cmdline(pid):
                try:
                    os.kill(pid, 9)
                    print(f"killed {pid}")
                except OSError:
                    pass


def _posix():
    cur = os.getpid()
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,args="], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        try:
            out = subprocess.run(["pgrep", "-f", PAT], capture_output=True, text=True).stdout
        except Exception:
            print("done")
            return
        for line in out.splitlines():
            try:
                pid = int(line.split()[0])
            except ValueError:
                continue
            if pid != cur:
                os.kill(pid, 9)
                print(f"killed {pid}")
        print("done")
        return
    import signal
    for line in out.splitlines():
        line = line.strip()
        if PAT not in line or "kill_overlay" in line:
            continue
        try:
            pid = int(line.split()[0])
        except ValueError:
            continue
        if pid != cur:
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"killed {pid}")
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    (_win if os.name == "nt" else _posix)()
    print("done")
