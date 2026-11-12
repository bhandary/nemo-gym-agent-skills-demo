#!/usr/bin/env bash
# Start one local TicketNow briefing server and wait until it can be used.
# Writes .verify-evidence/<timestamp>/ and points .verify-evidence/active at it.
# The page shows Recorded sample and Live model. Export DEMO_SHOW_MOCK=1
# before this script when the Mock model radio is part of the proof.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f .verify-evidence/active ]]; then
  existing="$(cat .verify-evidence/active)"
  if [[ -f "${existing}/server.pid" ]]; then
    old_pid="$(cat "${existing}/server.pid")"
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "A verification server is already running (pid ${old_pid})." >&2
      echo "Evidence: ${existing}" >&2
      echo "Run scripts/verify/cleanup.sh before starting another." >&2
      exit 1
    fi
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/ and rerun scripts/verify/launch.sh" >&2
  exit 1
fi
if [[ ! -d .venv ]]; then
  uv venv --python 3.13 .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if ! python -c "import fastapi, uvicorn, yaml, nemo_gym" >/dev/null 2>&1; then
  uv pip install "nemo-gym==0.7.0" pytest pyyaml
fi

port_open() {
  python - "$1" <<'PY'
import socket, sys
sock = socket.socket()
sock.settimeout(0.3)
code = sock.connect_ex(("127.0.0.1", int(sys.argv[1])))
sock.close()
sys.exit(0 if code == 0 else 1)
PY
}

if [[ -n "${VERIFY_PORT:-}" ]]; then
  PORT="$VERIFY_PORT"
  if port_open "$PORT"; then
    echo "Port ${PORT} is already in use. Pick another VERIFY_PORT." >&2
    exit 1
  fi
else
  PORT=""
  for candidate in $(seq 43124 43140); do
    if ! port_open "$candidate"; then
      PORT="$candidate"
      break
    fi
  done
  if [[ -z "$PORT" ]]; then
    echo "No free port between 43124 and 43140." >&2
    exit 1
  fi
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE="${ROOT}/.verify-evidence/${STAMP}"
mkdir -p "$EVIDENCE"
if [[ -f env.yaml ]]; then
  echo 1 >"${EVIDENCE}/env-yaml-existed"
else
  echo 0 >"${EVIDENCE}/env-yaml-existed"
fi

export PORT
export HOST="127.0.0.1"
# The app loads .env itself. Do not inject a key here.
nohup python -m web >>"${EVIDENCE}/server.log" 2>&1 &
pid="$!"
echo "$pid" >"${EVIDENCE}/server.pid"
printf '%s\n' "$EVIDENCE" >.verify-evidence/active

python3 - "$EVIDENCE" "$pid" "$PORT" <<'PY'
import json, sys
from datetime import datetime, timezone
path, pid, port = sys.argv[1:]
payload = {
    "pid": int(pid),
    "port": int(port),
    "host": "127.0.0.1",
    "base_url": f"http://127.0.0.1:{port}",
    "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "command": "python -m web",
}
open(f"{path}/launch.json", "w", encoding="utf-8").write(json.dumps(payload, indent=2) + "\n")
PY

ready=0
for _ in $(seq 1 60); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "The server exited before it was usable. Log:" >&2
    cat "${EVIDENCE}/server.log" >&2 || true
    exit 1
  fi
  health_ok=0
  briefing_ok=0
  if curl -sf "http://127.0.0.1:${PORT}/health" | python3 -c 'import json,sys; body=json.load(sys.stdin); raise SystemExit(0 if body.get("status")=="ok" and body.get("service")=="ticketnow-it-desk" and body.get("nemo_gym")=="0.7.0" else 1)' >/dev/null 2>&1; then
    health_ok=1
  fi
  if curl -sf "http://127.0.0.1:${PORT}/api/briefing" | python3 -c 'import json,sys; body=json.load(sys.stdin); modes=body.get("modes") or {}; raise SystemExit(0 if modes.get("recorded",{}).get("enabled") is True else 1)' >/dev/null 2>&1; then
    briefing_ok=1
  fi
  if [[ "$health_ok" -eq 1 && "$briefing_ok" -eq 1 ]]; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" -ne 1 ]]; then
  echo "The process stayed up but /health or /api/briefing never became usable." >&2
  cat "${EVIDENCE}/server.log" >&2 || true
  exit 1
fi

echo "TicketNow is usable at http://127.0.0.1:${PORT}"
echo "pid ${pid}"
echo "evidence ${EVIDENCE}"
