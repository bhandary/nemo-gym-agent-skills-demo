#!/usr/bin/env bash
# Stop only the server this skill started, then drop its scratch files.
# The evidence directory is kept.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EVIDENCE="${VERIFY_EVIDENCE:-}"
if [[ -z "$EVIDENCE" && -f .verify-evidence/active ]]; then
  EVIDENCE="$(cat .verify-evidence/active)"
fi
if [[ -z "$EVIDENCE" || ! -f "${EVIDENCE}/server.pid" ]]; then
  echo "No active verification server to stop."
  rm -f .verify-evidence/active
  exit 0
fi

pid="$(cat "${EVIDENCE}/server.pid")"
command=""
if [[ -r "/proc/${pid}/cmdline" ]]; then
  command="$(tr '\0' ' ' <"/proc/${pid}/cmdline")"
fi

if [[ -n "$command" ]]; then
  case "$command" in
    *python*-m\ web*)
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 30); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
      echo "Stopped pid ${pid}."
      ;;
    *)
      echo "Refusing to signal pid ${pid}; it is not python -m web (${command})." >&2
      exit 1
      ;;
  esac
else
  echo "pid ${pid} is already gone."
fi

if [[ -f "${EVIDENCE}/run-id" ]]; then
  run_id="$(tr -cd '0-9a-f' <"${EVIDENCE}/run-id")"
  if [[ "${#run_id}" -eq 12 && -d "results/ui/${run_id}" ]]; then
    rm -rf "results/ui/${run_id}"
    echo "Removed results/ui/${run_id}."
  fi
fi

if [[ -f "${EVIDENCE}/env-yaml-existed" && "$(cat "${EVIDENCE}/env-yaml-existed")" == "0" ]]; then
  rm -f env.yaml
fi

if [[ -f .verify-evidence/active && "$(cat .verify-evidence/active)" == "$EVIDENCE" ]]; then
  rm -f .verify-evidence/active
fi

echo "Evidence kept at ${EVIDENCE}"
