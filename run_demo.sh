#!/usr/bin/env bash
# One command for the Northwind Agent Skills demo.
# Starts NeMo Gym, runs the same five tickets three ways, and prints the comparison.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"
export NEMO_GYM_EXTRA_ROOTS="$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/ and rerun ./run_demo.sh"
  exit 1
fi

if [[ ! -d .venv ]]; then
  uv venv --python 3.13.14 .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import nemo_gym, pytest" >/dev/null 2>&1; then
  uv pip install "nemo-gym==0.7.0" pytest
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

python - <<'PY'
from pathlib import Path
from demo.skill_sets import sync_without_refund
from resources_servers.northwind_desk.policy import render_tasks_jsonl

root = Path(".")
sync_without_refund(root)
data = root / "resources_servers" / "northwind_desk" / "data"
data.mkdir(parents=True, exist_ok=True)
(data / "tasks.jsonl").write_text(render_tasks_jsonl(), encoding="utf-8")
PY

echo "Running unit tests before the servers start."
python -m pytest -q

key="${POLICY_API_KEY:-}"
real_key=0
case "$key" in
  ""|mock|changeme|CHANGEME|your-key|your-api-key|sk-your-key-here|replace-me) real_key=0 ;;
  *) real_key=1 ;;
esac

MOCK_PID=""
GYM_PID=""
cleanup() {
  local status=$?
  if [[ -n "$GYM_PID" ]] && kill -0 "$GYM_PID" 2>/dev/null; then
    kill -INT "$GYM_PID" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8; do
      kill -0 "$GYM_PID" 2>/dev/null || break
      sleep 1
    done
    kill -KILL "$GYM_PID" 2>/dev/null || true
    wait "$GYM_PID" 2>/dev/null || true
  fi
  if [[ -n "$MOCK_PID" ]] && kill -0 "$MOCK_PID" 2>/dev/null; then
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

mkdir -p results
MODEL_TYPE="${POLICY_MODEL_TYPE:-vllm_model}"
if [[ "$real_key" -eq 0 ]]; then
  echo "No policy API key is set. Using the deterministic mock model (mock-desk-associate)."
  echo "This run is MOCK output. It is not a call to NVIDIA or OpenAI."
  python -m demo.mock_model >/tmp/northwind-mock.log 2>&1 &
  MOCK_PID=$!
  for _ in $(seq 1 50); do
    if curl -sf "http://127.0.0.1:43117/v1/models" >/dev/null; then
      break
    fi
    if ! kill -0 "$MOCK_PID" 2>/dev/null; then
      echo "The mock model exited."
      cat /tmp/northwind-mock.log
      exit 1
    fi
    sleep 0.1
  done
  export POLICY_BASE_URL="http://127.0.0.1:43117/v1"
  export POLICY_API_KEY="mock"
  export POLICY_MODEL_NAME="mock-desk-associate"
  MODEL_TYPE="vllm_model"
else
  : "${POLICY_BASE_URL:?Set POLICY_BASE_URL in .env}"
  : "${POLICY_MODEL_NAME:?Set POLICY_MODEL_NAME in .env}"
  echo "Using ${MODEL_TYPE} at ${POLICY_BASE_URL} model ${POLICY_MODEL_NAME}."
fi

export POLICY_MODEL_TYPE="$MODEL_TYPE"
python - <<'PY'
import os
from pathlib import Path

import yaml

cfg = {
    "policy_base_url": os.environ["POLICY_BASE_URL"],
    "policy_api_key": os.environ["POLICY_API_KEY"],
    "policy_model_name": os.environ["POLICY_MODEL_NAME"],
    "uv_venv_dir": ".gym_venvs",
    "server_spinup_timeout_seconds": 1200,
}
# Hydra rejects a dotted override for a server that is loaded from another file.
# env.yaml is merged after those files, so the flags land on the vllm server.
if os.environ.get("POLICY_MODEL_TYPE", "vllm_model") == "vllm_model" and os.environ.get(
    "POLICY_REASONING_PARSER", "false"
).lower() not in {"1", "true", "yes"}:
    cfg["policy_model"] = {
        "responses_api_models": {
            "vllm_model": {
                "uses_reasoning_parser": False,
                "uses_interleaved_reasoning": False,
            }
        }
    }
Path("env.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
PY

echo "Starting NeMo Gym. The first start builds one virtualenv per server and can take several minutes."
gym env start \
  --resources-server northwind_desk \
  --model-type "$MODEL_TYPE" \
  >results/servers.log 2>&1 &
GYM_PID=$!

ready=0
for _ in $(seq 1 400); do
  if ! kill -0 "$GYM_PID" 2>/dev/null; then
    echo "gym env start exited before the servers were ready. Last log lines:"
    tail -n 120 results/servers.log || true
    exit 1
  fi
  if curl -sf "http://127.0.0.1:11000/readyz" >/dev/null; then
    ready=1
    break
  fi
  sleep 3
done
if [[ "$ready" -ne 1 ]]; then
  echo "Timed out waiting for NeMo Gym. Last log lines:"
  tail -n 120 results/servers.log || true
  exit 1
fi
echo "Servers are ready."

run_variant() {
  local name="$1"
  shift
  echo "Collecting ${name}."
  if ! gym eval run \
    --no-serve \
    --agent northwind_desk_skills_agent \
    --input resources_servers/northwind_desk/data/tasks.jsonl \
    --output "results/${name}.jsonl" \
    --concurrency 1 \
    --num-repeats 1 \
    --temperature "${DEMO_TEMPERATURE:-0}" \
    "$@" \
    >"results/${name}.log" 2>&1; then
    echo "gym eval run failed for ${name}. Last log lines:"
    tail -n 80 "results/${name}.log" || true
    exit 1
  fi
}

run_variant no_skills
run_variant full_skills +skills.path=skills/full
run_variant without_refund_policy +skills.path=skills/without_refund_policy

python -m demo.report --results results
echo
if [[ "$real_key" -eq 0 ]]; then
  echo "Demo finished. Results are in results/. This run used the mock model, not a live API."
  echo "A recorded copy of a mock run is in sample_run/ if you need slides before the servers finish."
else
  echo "Demo finished. Results are in results/. Model: ${POLICY_MODEL_NAME}."
fi
echo "Comparison: results/comparison.md"
echo "Trace:      results/trace.md"
