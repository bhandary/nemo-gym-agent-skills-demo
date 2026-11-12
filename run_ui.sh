#!/usr/bin/env bash
# Briefing page. Recorded sample works as soon as the process is up.
# Run starts a live model. The page has no mode control.
# POST /api/runs still accepts mode=recorded and mode=mock.
# DEMO_SHOW_RECORDED=1 shows the saved sample. DEMO_SHOW_MOCK=1 makes Run start the local mock.
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
