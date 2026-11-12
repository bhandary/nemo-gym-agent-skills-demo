#!/usr/bin/env bash
# Briefing page. Recorded sample works as soon as the process is up.
# Live model starts NeMo Gym only after you press Run demo.
# Mock model stays off the page unless DEMO_SHOW_MOCK=1. POST /api/runs still accepts mode=mock.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/ and rerun ./run_ui.sh"
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

exec python -m web
