#!/usr/bin/env bash
# Read-only check of the verification server this skill started.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EVIDENCE="${VERIFY_EVIDENCE:-}"
if [[ -z "$EVIDENCE" && -f .verify-evidence/active ]]; then
  EVIDENCE="$(cat .verify-evidence/active)"
fi
if [[ -z "$EVIDENCE" || ! -f "${EVIDENCE}/launch.json" ]]; then
  echo "No active verification server. Run scripts/verify/launch.sh first." >&2
  exit 1
fi

python3 - "$ROOT" "$EVIDENCE" <<'PY'
import json, os, socket, sys
from pathlib import Path

root = Path(sys.argv[1])
evidence = Path(sys.argv[2])
launch = json.loads((evidence / "launch.json").read_text(encoding="utf-8"))
pid = int(launch["pid"])
port = int(launch["port"])
base = launch["base_url"]
problems = []

def cmdline(check_pid: int) -> str:
    try:
        raw = Path(f"/proc/{check_pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()

def listening_inodes(wanted_port: int) -> set[str]:
    found = set()
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        path = Path(name)
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]
        for line in lines:
            parts = line.split()
            local, state, inode = parts[1], parts[3], parts[9]
            if state != "0A":
                continue
            local_port = int(local.rsplit(":", 1)[1], 16)
            if local_port == wanted_port:
                found.add(inode)
    return found

def process_owns_inodes(check_pid: int, inodes: set[str]) -> bool:
    fd_dir = Path(f"/proc/{check_pid}/fd")
    if not fd_dir.is_dir() or not inodes:
        return False
    for entry in fd_dir.iterdir():
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            return True
    return False

command = cmdline(pid)
if not command:
    problems.append(f"pid {pid} is not running")
elif "python" not in command or "-m web" not in command:
    problems.append(f"pid {pid} is not the server this launch started ({command!r})")

inodes = listening_inodes(port)
if not inodes:
    problems.append(f"nothing is listening on {port}")
elif command and not process_owns_inodes(pid, inodes):
    problems.append(f"port {port} is not owned by pid {pid}")

health = {}
briefing = {}
try:
    import urllib.request
    with urllib.request.urlopen(base + "/health", timeout=5) as response:
        health = json.loads(response.read().decode())
    with urllib.request.urlopen(base + "/api/briefing", timeout=5) as response:
        briefing = json.loads(response.read().decode())
except Exception as exc:
    problems.append(f"read-only HTTP check failed: {exc}")

if health:
    if health.get("status") != "ok":
        problems.append(f"health status is {health.get('status')!r}")
    if health.get("service") != "ticketnow-it-desk":
        problems.append(f"service is {health.get('service')!r}")
    if health.get("nemo_gym") != "0.7.0":
        problems.append(f"nemo_gym is {health.get('nemo_gym')!r}, expected 0.7.0")

modes = {}
if briefing:
    for name, info in (briefing.get("modes") or {}).items():
        modes[name] = {"enabled": bool(info.get("enabled")), "reason": info.get("reason") or "", "detail": info.get("detail") or ""}
    if "recorded" not in modes or "mock" not in modes or "live" not in modes:
        problems.append("briefing did not list recorded, mock, and live")

def port_open(number: int) -> bool:
    sock = socket.socket()
    sock.settimeout(0.3)
    code = sock.connect_ex(("127.0.0.1", number))
    sock.close()
    return code == 0

report = {
    "ok": not problems,
    "pid": pid,
    "port": port,
    "base_url": base,
    "cmdline": command,
    "health": health,
    "modes": modes,
    "gym_port_11000_in_use": port_open(11000),
    "mock_port_43117_in_use": port_open(43117),
    "problems": problems,
}
(evidence / "doctor.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(0 if report["ok"] else 1)
PY
