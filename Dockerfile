# One service. The page and the recorded sample are in the image.
# Mock and live runs install NeMo Gym's per-server virtualenvs on first use.
# Prebuilding those virtualenvs copies Ray and the model server's dev extra,
# which pushed the image past a practical Railway size.

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
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

RUN useradd --create-home --uid 10001 --shell /bin/bash northwind \
    && chown northwind:northwind /app

COPY --chown=northwind:northwind . /app

USER northwind
ENV HOME=/home/northwind

RUN uv venv --python 3.13 /app/.venv \
    && uv pip install --python /app/.venv/bin/python "nemo-gym==0.7.0" pytest pyyaml \
    && rm -rf /home/northwind/.cache/uv

EXPOSE 8080
CMD ["python", "-m", "web"]
