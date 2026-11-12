# One service. The page, the recorded sample, and the NeMo Gym server
# virtualenvs are in the image. Mock and Live start Ray, but they do not
# install those environments on first use.
# Hardlinks share one copy of the packages across the parent venv and the
# server venvs. The uv cache is deleted in the same layer.

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=hardlink \
    UV_CACHE_DIR=/app/.uv-cache \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NEMO_GYM_EXTRA_ROOTS=/app \
    PATH="/app/.venv/bin:${PATH}" \
    PORT=8080 \
    HOST=0.0.0.0 \
    RAY_AUTH_MODE=disabled \
    RAY_DEFAULT_OBJECT_STORE_MAX_MEMORY_BYTES=134217728 \
    RAY_DEFAULT_OBJECT_STORE_MEMORY_PROPORTION=0.08 \
    RAY_DISABLE_DOCKER_CPU_WARNING=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /bin/bash ticketnow \
    && chown ticketnow:ticketnow /app

COPY --chown=ticketnow:ticketnow . /app

USER ticketnow
ENV HOME=/home/ticketnow

RUN uv venv --python 3.13 /app/.venv \
    && uv pip install --python /app/.venv/bin/python "nemo-gym==0.7.0" pytest pyyaml \
    && /app/.venv/bin/python -c 'from pathlib import Path; import yaml; Path("/app/env.yaml").write_text(yaml.safe_dump({"policy_base_url": "http://127.0.0.1:9/v1", "policy_api_key": "build", "policy_model_name": "prefetch", "uv_venv_dir": ".gym_venvs", "uv_cache_dir": "/app/.uv-cache", "skip_venv_if_present": True}))' \
    && gym env prefetch --resources-server ticketnow_desk --model-type vllm_model \
    && gym env prefetch --resources-server ticketnow_desk --model-type openai_model \
    && rm -f /app/env.yaml \
    && rm -rf /app/.uv-cache /app/cache /home/ticketnow/.cache \
    && find /app -type d -name __pycache__ -print0 | xargs -0r rm -rf \
    && test -x /app/.gym_venvs/responses_api_models/vllm_model/.venv/bin/python \
    && test -x /app/.gym_venvs/responses_api_models/openai_model/.venv/bin/python \
    && test ! -f /app/env.yaml

EXPOSE 8080
CMD ["python", "-m", "web"]
