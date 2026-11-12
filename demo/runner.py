"""Run the three Northwind configurations through NeMo Gym.

The briefing page calls this for Mock model and Live model. Recorded sample
never reaches it. The CLI in ``run_demo.sh`` stays the terminal path.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

from demo.present import build_view
from demo.report import write_report
from demo.settings import ModelSettings, model_settings, nemo_gym_version
from demo.skill_sets import sync_without_refund
from resources_servers.northwind_desk.policy import render_tasks_jsonl


StepCallback = Callable[[str, str, str], None]

MOCK_PORT = 43117
GYM_PORT = 11000
READY_URL = f"http://127.0.0.1:{GYM_PORT}/readyz"
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1/models"

VARIANTS = (
    ("no_skills", "Score the tickets with no skills", []),
    ("full_skills", "Score the tickets with all three skills", ["+skills.path=skills/full"]),
    (
        "without_refund_policy",
        "Score the tickets with the refund skill removed",
        ["+skills.path=skills/without_refund_policy"],
    ),
)


class DemoRunError(Exception):
    def __init__(self, message: str, log_tail: str = "") -> None:
        super().__init__(message)
        self.log_tail = log_tail


def port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def gym_on_path(root: Path) -> str | None:
    bindir = root / ".venv" / "bin"
    candidate = bindir / "gym"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    found = _which("gym")
    return found


def gym_available(root: Path) -> tuple[bool, str]:
    if gym_on_path(root):
        return True, ""
    return (
        False,
        "The gym command is not installed in this environment. Recorded sample still works.",
    )


def model_env(mode: str, source: Mapping[str, str] | None = None) -> dict[str, str]:
    if mode == "mock":
        return {
            "POLICY_BASE_URL": f"http://127.0.0.1:{MOCK_PORT}/v1",
            "POLICY_API_KEY": "mock",
            "POLICY_MODEL_NAME": "mock-desk-associate",
            "POLICY_MODEL_TYPE": "vllm_model",
            "POLICY_REASONING_PARSER": "false",
        }
    if mode != "live":
        raise DemoRunError(f"Unknown run mode {mode}.")
    settings = model_settings(source)
    if not settings.live:
        raise DemoRunError(settings.live_reason or "Live mode is not configured on the server.")
    return {
        "POLICY_BASE_URL": settings.base_url,
        "POLICY_API_KEY": settings.api_key,
        "POLICY_MODEL_NAME": settings.model_name,
        "POLICY_MODEL_TYPE": settings.model_type,
        "POLICY_REASONING_PARSER": "true" if settings.reasoning_parser else "false",
        "DEMO_TEMPERATURE": settings.temperature,
    }


def write_env_yaml(path: Path, env: Mapping[str, str]) -> None:
    model_type = env.get("POLICY_MODEL_TYPE", "vllm_model")
    cfg: dict[str, Any] = {
        "policy_base_url": env["POLICY_BASE_URL"],
        "policy_api_key": env["POLICY_API_KEY"],
        "policy_model_name": env["POLICY_MODEL_NAME"],
        "uv_venv_dir": ".gym_venvs",
        "server_spinup_timeout_seconds": 1200,
        "skip_venv_if_present": True,
        "model_endpoint_readiness_timeout_seconds": 120,
    }
    reasoning = env.get("POLICY_REASONING_PARSER", "false").lower() in {"1", "true", "yes"}
    if model_type == "vllm_model" and not reasoning:
        cfg["policy_model"] = {
            "responses_api_models": {
                "vllm_model": {
                    "uses_reasoning_parser": False,
                    "uses_interleaved_reasoning": False,
                }
            }
        }
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    path.chmod(0o600)


def _which(name: str) -> str | None:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    for entry in paths:
        candidate = Path(entry) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 0) < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _endpoint_answers(url: str, timeout: float = 5.0) -> bool:
    """Any HTTP response counts. A refused connection does not."""
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status > 0
    except HTTPError:
        return True
    except (URLError, TimeoutError, OSError):
        return False


def _tail(path: Path, limit: int = 40) -> str:
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [line for line in lines if line.strip()]
    return "\n".join(kept[-limit:])


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[redacted]")
    return text


def _last_line(path: Path) -> str:
    tail = _tail(path, limit=8)
    if not tail:
        return ""
    line = tail.splitlines()[-1].strip()
    if len(line) > 180:
        return line[:179] + "…"
    return line


def _child_env(root: Path, policy: Mapping[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(policy)
    bindir = root / ".venv" / "bin"
    if bindir.is_dir():
        env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    env["NEMO_GYM_EXTRA_ROOTS"] = str(root)
    env["PYTHONUNBUFFERED"] = "1"
    env["RAY_AUTH_MODE"] = "disabled"
    env["RAY_DEFAULT_OBJECT_STORE_MAX_MEMORY_BYTES"] = os.environ.get(
        "RAY_DEFAULT_OBJECT_STORE_MAX_MEMORY_BYTES", "134217728"
    )
    env["RAY_DEFAULT_OBJECT_STORE_MEMORY_PROPORTION"] = os.environ.get(
        "RAY_DEFAULT_OBJECT_STORE_MEMORY_PROPORTION", "0.08"
    )
    env.setdefault("RAY_DISABLE_DOCKER_CPU_WARNING", "1")
    return env


def _venvs_ready(root: Path, model_type: str) -> bool:
    model_dir = "vllm_model" if model_type == "vllm_model" else "openai_model"
    needed = [
        root / ".gym_venvs/resources_servers/northwind_desk/.venv/bin/python",
        root / ".gym_venvs/responses_api_agents/desk_skills_agent/.venv/bin/python",
        root / ".gym_venvs/environment_servers/legacy_agent/.venv/bin/python",
        root / f".gym_venvs/responses_api_models/{model_dir}/.venv/bin/python",
    ]
    return all(path.is_file() for path in needed)


def _kill_process_group(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.killpg(pid, signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        return
    for _ in range(8):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.4)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return


def _source_label(mode: str, settings_env: Mapping[str, str]) -> tuple[str, str, str]:
    version = nemo_gym_version()
    if mode == "mock":
        return (
            "This run executed inside NeMo Gym against the local mock model "
            f"mock-desk-associate. NeMo Gym {version}. This is not a call to NVIDIA or OpenAI.",
            "mock-desk-associate",
            f"127.0.0.1:{MOCK_PORT}",
        )
    settings = model_settings(settings_env)
    return (
        f"This run executed inside NeMo Gym against {settings.model_name} "
        f"at {settings.endpoint_host}. NeMo Gym {version}.",
        settings.model_name,
        settings.endpoint_host,
    )


def execute_gym_run(
    *,
    root: Path,
    mode: str,
    run_id: str,
    on_step: StepCallback,
    on_spawn: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    if mode not in {"mock", "live"}:
        raise DemoRunError("NeMo Gym runs from Mock model or Live model.")
    policy = model_env(mode)
    if port_in_use(GYM_PORT):
        raise DemoRunError(
            "NeMo Gym is already running on port 11000. Stop the other demo "
            "(a terminal ./run_demo.sh, or another briefing run) and try again. "
            "Recorded sample does not need those servers."
        )
    gym_bin = gym_on_path(root)
    if not gym_bin:
        raise DemoRunError(gym_available(root)[1])

    results = root / "results" / "ui" / run_id
    results.mkdir(parents=True, exist_ok=True)
    secrets = [policy.get("POLICY_API_KEY", "")]
    mock_pid: int | None = None
    gym_pid: int | None = None
    servers_log = results / "servers.log"

    try:
        on_step("prepare", "running", "Writing the five tickets and the skill folders.")
        sync_without_refund(root)
        data = root / "resources_servers" / "northwind_desk" / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "tasks.jsonl").write_text(render_tasks_jsonl(), encoding="utf-8")
        on_step("prepare", "done", "Five tickets are ready. The task file does not name a skill.")

        if mode == "mock":
            if port_in_use(MOCK_PORT):
                raise DemoRunError(
                    f"Port {MOCK_PORT} is already in use, so the mock model cannot start. "
                    "Recorded sample does not need it."
                )
            on_step("model", "running", "Starting mock-desk-associate.")
            mock_log = results / "mock.log"
            with mock_log.open("w", encoding="utf-8") as handle:
                mock = subprocess.Popen(
                    [sys.executable, "-m", "demo.mock_model"],
                    cwd=root,
                    env=_child_env(root, policy),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            mock_pid = mock.pid
            if on_spawn:
                on_spawn(mock_pid)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if mock.poll() is not None:
                    raise DemoRunError(
                        "The mock model exited before it could answer.",
                        _scrub(_tail(mock_log), secrets),
                    )
                if _http_ok(MOCK_URL):
                    break
                time.sleep(0.1)
            else:
                raise DemoRunError(
                    "The mock model did not answer on port 43117.",
                    _scrub(_tail(mock_log), secrets),
                )
            on_step(
                "model",
                "done",
                "Mock model is answering. This is not a live NVIDIA or OpenAI model.",
            )
        else:
            host = model_settings(policy).endpoint_host
            on_step("model", "running", f"Checking the live endpoint at {host}.")
            probe = policy["POLICY_BASE_URL"].rstrip("/")
            probe_url = f"{probe}/models" if probe.endswith("/v1") else probe
            if not _endpoint_answers(probe_url):
                raise DemoRunError(
                    f"Nothing answered at {host}. Check POLICY_BASE_URL on the server. "
                    "The browser does not collect a replacement key."
                )
            on_step("model", "done", f"Live endpoint {host} answered.")

        write_env_yaml(root / "env.yaml", policy)
        model_type = policy["POLICY_MODEL_TYPE"]
        ready_seconds = 240 if _venvs_ready(root, model_type) else 1200
        on_step("gym", "running", "Starting the head server, the desk, and the verifier.")
        with servers_log.open("w", encoding="utf-8") as handle:
            gym = subprocess.Popen(
                [
                    gym_bin,
                    "env",
                    "start",
                    "--resources-server",
                    "northwind_desk",
                    "--model-type",
                    model_type,
                ],
                cwd=root,
                env=_child_env(root, policy),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        gym_pid = gym.pid
        if on_spawn:
            on_spawn(gym_pid)
        deadline = time.monotonic() + ready_seconds
        next_detail = 0.0
        while time.monotonic() < deadline:
            if gym.poll() is not None:
                tail = _scrub(_tail(servers_log), secrets)
                raise DemoRunError(_gym_failed_message(tail), tail)
            if _http_ok(READY_URL, timeout=3):
                break
            now = time.monotonic()
            if now >= next_detail:
                line = _scrub(_last_line(servers_log), secrets)
                detail = "Waiting until NeMo Gym reports ready."
                if not _venvs_ready(root, model_type):
                    detail = "First start installs one virtualenv per server. That can take several minutes."
                if line:
                    detail = f"{detail} {line}"
                on_step("gym", "running", detail)
                next_detail = now + 4
            time.sleep(1)
        else:
            tail = _scrub(_tail(servers_log), secrets)
            raise DemoRunError(
                "NeMo Gym did not become ready in time. "
                + _ray_hint(tail),
                tail,
            )
        on_step("gym", "done", "NeMo Gym is ready.")

        temperature = policy.get("DEMO_TEMPERATURE") or os.environ.get("DEMO_TEMPERATURE", "0") or "0"
        for key, _label, extra in VARIANTS:
            on_step(key, "running", "NeMo Gym is collecting five rollouts.")
            log_path = results / f"{key}.log"
            command = [
                gym_bin,
                "eval",
                "run",
                "--no-serve",
                "--agent",
                "northwind_desk_skills_agent",
                "--input",
                "resources_servers/northwind_desk/data/tasks.jsonl",
                "--output",
                str(results / f"{key}.jsonl"),
                "--concurrency",
                "1",
                "--num-repeats",
                "1",
                "--temperature",
                temperature,
                *extra,
            ]
            with log_path.open("w", encoding="utf-8") as handle:
                completed = subprocess.run(
                    command,
                    cwd=root,
                    env=_child_env(root, policy),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            if completed.returncode != 0:
                tail = _scrub(_tail(log_path), secrets)
                raise DemoRunError(f"Scoring {key.replace('_', ' ')} failed.", tail)
            on_step(key, "done", "Five rollouts scored.")

        on_step("report", "running", "Comparing the three runs.")
        label, model_name, host = _source_label(mode, policy)
        write_report(results, results / "comparison.md", results / "trace.md", "dented-kettle")
        banner = f"> {label}\n\n"
        for name in ("comparison.md", "trace.md"):
            target = results / name
            target.write_text(banner + target.read_text(encoding="utf-8"), encoding="utf-8")
        view = build_view(
            results,
            kind=mode,
            source_label=label,
            model=model_name,
            nemo_gym=nemo_gym_version(),
            endpoint_host=host,
        )
        on_step("report", "done", "Comparison ready.")
        return view
    finally:
        _kill_process_group(gym_pid)
        _kill_process_group(mock_pid)


def _ray_hint(tail: str) -> str:
    lowered = tail.lower()
    if any(token in lowered for token in ("ray", "shm", "object store", "memory")):
        return (
            "Ray did not stay up in this container. Give the service more memory, "
            "or keep presenting from Recorded sample, which does not start Ray."
        )
    return "The server log is below. Recorded sample does not start NeMo Gym."


def _gym_failed_message(tail: str) -> str:
    return "NeMo Gym stopped before the servers were ready. " + _ray_hint(tail)


def run_steps(mode: str) -> list[dict[str, str]]:
    """Checklist shown while a run is in progress. Recorded sample completes it at once."""
    if mode == "recorded":
        return [
            {"id": "prepare", "label": "Prepare the five tickets", "state": "done", "detail": "Using the tickets from the recorded run."},
            {"id": "model", "label": "Call a model", "state": "done", "detail": "No model was called. The recording used mock-desk-associate."},
            {"id": "gym", "label": "Start NeMo Gym", "state": "done", "detail": "NeMo Gym already scored this recording."},
            {"id": "no_skills", "label": "Score the tickets with no skills", "state": "done", "detail": "Loaded from sample_run."},
            {"id": "full_skills", "label": "Score the tickets with all three skills", "state": "done", "detail": "Loaded from sample_run."},
            {"id": "without_refund_policy", "label": "Score the tickets with the refund skill removed", "state": "done", "detail": "Loaded from sample_run."},
            {"id": "report", "label": "Build the comparison", "state": "done", "detail": "Comparison ready."},
        ]
    model_label = "Start the mock model" if mode == "mock" else "Check the live model"
    return [
        {"id": "prepare", "label": "Prepare the five tickets", "state": "pending", "detail": ""},
        {"id": "model", "label": model_label, "state": "pending", "detail": ""},
        {"id": "gym", "label": "Start NeMo Gym", "state": "pending", "detail": ""},
        {"id": "no_skills", "label": "Score the tickets with no skills", "state": "pending", "detail": ""},
        {"id": "full_skills", "label": "Score the tickets with all three skills", "state": "pending", "detail": ""},
        {"id": "without_refund_policy", "label": "Score the tickets with the refund skill removed", "state": "pending", "detail": ""},
        {"id": "report", "label": "Build the comparison", "state": "pending", "detail": ""},
    ]
