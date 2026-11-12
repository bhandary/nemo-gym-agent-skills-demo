"""Environment for the policy model.

The browser never sends a key. Live mode turns on only when the server
process already has a real ``POLICY_API_KEY``, a base URL, and a model name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


NEMO_GYM_VERSION_FALLBACK = "0.7.0"

# Keep this aligned with the placeholder list in run_demo.sh.
PLACEHOLDER_KEYS = {
    "",
    "mock",
    "changeme",
    "your-key",
    "your-api-key",
    "sk-your-key-here",
    "replace-me",
    "paste-your-key",
}


def is_real_key(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() not in PLACEHOLDER_KEYS


def nemo_gym_version() -> str:
    try:
        from importlib.metadata import version

        return version("nemo-gym")
    except Exception:
        return NEMO_GYM_VERSION_FALLBACK


def load_dotenv(path: str | os.PathLike[str]) -> None:
    """Load ``.env`` without overriding variables the process already has."""
    file_path = os.fspath(path)
    if not os.path.isfile(file_path):
        return
    with open(file_path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                os.environ.setdefault(key, value)


@dataclass(frozen=True)
class ModelSettings:
    base_url: str
    api_key: str
    model_name: str
    model_type: str
    reasoning_parser: bool
    temperature: str
    live: bool
    live_reason: str

    @property
    def endpoint_host(self) -> str:
        url = self.base_url.strip()
        if "://" in url:
            host = url.split("://", 1)[1]
        else:
            host = url
        host = host.split("/", 1)[0]
        return host


def model_settings(env: Mapping[str, str] | None = None) -> ModelSettings:
    source = os.environ if env is None else env
    api_key = source.get("POLICY_API_KEY", "")
    base_url = source.get("POLICY_BASE_URL", "").strip()
    model_name = (source.get("POLICY_MODEL_NAME") or source.get("POLICY_MODEL") or "").strip()
    model_type = (source.get("POLICY_MODEL_TYPE") or "vllm_model").strip()
    reasoning_parser = source.get("POLICY_REASONING_PARSER", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    temperature = source.get("DEMO_TEMPERATURE", "0").strip() or "0"

    live = True
    reason = ""
    if not is_real_key(api_key):
        live = False
        if api_key.strip():
            reason = "POLICY_API_KEY is still a placeholder. Live mode stays off."
        else:
            reason = (
                "Live mode stays off until POLICY_API_KEY is set on the server. "
                "The page never asks for a key."
            )
    elif not base_url:
        live = False
        reason = "POLICY_BASE_URL is not set on the server."
    elif not model_name:
        live = False
        reason = "POLICY_MODEL_NAME is not set on the server. POLICY_MODEL is accepted as an alias."
    elif model_type not in {"vllm_model", "openai_model"}:
        live = False
        reason = "POLICY_MODEL_TYPE must be vllm_model or openai_model."

    return ModelSettings(
        base_url=base_url,
        api_key=api_key.strip(),
        model_name=model_name,
        model_type=model_type,
        reasoning_parser=reasoning_parser,
        temperature=temperature,
        live=live,
        live_reason=reason,
    )
