"""Run the three TicketNow configurations through NeMo Gym.

The briefing page calls this for Mock model and Live model. Recorded sample
never reaches it. The CLI in ``run_demo.sh`` stays the terminal path.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

from demo.present import build_view
from demo.report import write_report
from demo.settings import ModelSettings, model_settings, nemo_gym_version
from demo.skill_sets import materialize, run_plan
from resources_servers.ticketnow_desk.policy import CASES, render_tasks_jsonl


StepCallback = Callable[[str, str, str], None]
LogCallback = Callable[[str], None]

MOCK_PORT = 43117
GYM_PORT = 11000
READY_URL = f"http://127.0.0.1:{GYM_PORT}/readyz"
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1/models"
READY_WITH_VENVS_SECONDS = 180
READY_WITHOUT_VENVS_SECONDS = 300
LOG_STALL_SECONDS = 90
LOG_TAIL_LINES = 200

VARIANTS = tuple(
    (item["id"], f"Score the tickets: {item['label']}", [f"+skills.path={item['path']}"] if item["path"] else [])
    for item in run_plan()
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
            "POLICY_MODEL_NAME": "mock-it-lead",
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


def clip_log(text: str, limit: int = LOG_TAIL_LINES) -> str:
    kept = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(kept[-limit:])


def _tail(path: Path, limit: int = LOG_TAIL_LINES) -> str:
    if not path.is_file():
        return ""
    return clip_log(path.read_text(encoding="utf-8", errors="replace"), limit)


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
    env["RAY_OBJECT_STORE_ALLOW_SLOW_STORAGE"] = "1"
    env["RAY_LOG_TO_STDERR"] = "1"
    env["RAY_DEFAULT_OBJECT_STORE_MAX_MEMORY_BYTES"] = os.environ.get(
        "RAY_DEFAULT_OBJECT_STORE_MAX_MEMORY_BYTES", "209715200"
    )
    env["RAY_DEFAULT_OBJECT_STORE_MEMORY_PROPORTION"] = os.environ.get(
        "RAY_DEFAULT_OBJECT_STORE_MEMORY_PROPORTION", "0.08"
    )
    env.setdefault("RAY_DISABLE_DOCKER_CPU_WARNING", "1")
    pythonpath = env.get("PYTHONPATH", "")
    root_entry = str(root)
    entries = [entry for entry in pythonpath.split(os.pathsep) if entry]
    if root_entry not in entries:
        entries.insert(0, root_entry)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


def gym_command(root: Path) -> list[str]:
    """Run the Gym CLI through the wrapper that pins Ray before the cluster starts."""
    gym_bin = gym_on_path(root)
    if not gym_bin:
        raise DemoRunError(gym_available(root)[1])
    python = Path(gym_bin).resolve().parent / "python"
    if not python.is_file():
        python = Path(sys.executable)
    return [str(python), "-m", "demo.gym_main"]


def _pump_output(
    stream,
    logs: list[Path],
    prefix: str,
    secrets: list[str],
) -> None:
    """Copy a process stream into the full log files and the container stdout."""
    handles = [path.open("a", encoding="utf-8", errors="replace") for path in logs]
    try:
        while True:
            chunk = stream.readline()
            if not chunk:
                break
            text = _scrub(chunk.decode("utf-8", errors="replace"), secrets)
            for handle in handles:
                handle.write(text)
                handle.flush()
            sys.stdout.write(prefix + text)
            sys.stdout.flush()
    finally:
        for handle in handles:
            handle.close()
        stream.close()


def _popen_logged(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    logs: list[Path],
    prefix: str,
    secrets: list[str],
) -> subprocess.Popen:
    for path in logs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    assert process.stdout is not None
    thread = threading.Thread(
        target=_pump_output,
        args=(process.stdout, logs, prefix, secrets),
        name=f"log-{prefix.strip()}",
        daemon=True,
    )
    thread.start()
    process._log_thread = thread  # type: ignore[attr-defined]
    return process


def _wait_logged(process: subprocess.Popen) -> int:
    code = process.wait()
    thread = getattr(process, "_log_thread", None)
    if thread is not None:
        thread.join(timeout=5)
    return code


def venvs_ready(root: Path, model_type: str) -> bool:
    model_dir = "vllm_model" if model_type == "vllm_model" else "openai_model"
    needed = [
        root / ".gym_venvs/resources_servers/ticketnow_desk/.venv/bin/python",
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
            f"mock-it-lead. NeMo Gym {version}. This is not a call to NVIDIA or OpenAI.",
            "mock-it-lead",
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
    on_log: LogCallback | None = None,
    variants: list[dict[str, Any]] | None = None,
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
    gym_cmd = gym_command(root)

    results = root / "results" / "ui" / run_id
    results.mkdir(parents=True, exist_ok=True)
    secrets = [policy.get("POLICY_API_KEY", "")]
    mock_pid: int | None = None
    gym_pid: int | None = None
    servers_log = results / "servers.log"

    try:
        count = len(CASES)
        plan = variants if variants is not None else list(run_plan())
        on_step("prepare", "running", f"Writing the {count} tickets and the skill folders.")
        for item in plan:
            materialize(root, item)
        data = root / "resources_servers" / "ticketnow_desk" / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "tasks.jsonl").write_text(render_tasks_jsonl(), encoding="utf-8")
        on_step("prepare", "done", f"{count} tickets are ready. The task file does not name a skill.")

        if mode == "mock":
            if port_in_use(MOCK_PORT):
                raise DemoRunError(
                    f"Port {MOCK_PORT} is already in use, so the mock model cannot start. "
                    "Recorded sample does not need it."
                )
            on_step("model", "running", "Starting mock-it-lead.")
            mock_log = results / "mock.log"
            run_log = results / "run.log"
            mock = _popen_logged(
                [sys.executable, "-m", "demo.mock_model"],
                cwd=root,
                env=_child_env(root, policy),
                logs=[mock_log, run_log],
                prefix="[mock] ",
                secrets=secrets,
            )
            mock_pid = mock.pid
            if on_spawn:
                on_spawn(mock_pid)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if mock.poll() is not None:
                    _wait_logged(mock)
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
        installed = venvs_ready(root, model_type)
        ready_seconds = READY_WITH_VENVS_SECONDS if installed else READY_WITHOUT_VENVS_SECONDS
        on_step("gym", "running", "Starting the head server, the desk, and the verifier.")
        run_log = results / "run.log"
        gym = _popen_logged(
            [
                *gym_cmd,
                "env",
                "start",
                "--resources-server",
                "ticketnow_desk",
                "--model-type",
                model_type,
            ],
            cwd=root,
            env=_child_env(root, policy),
            logs=[servers_log, run_log],
            prefix="[gym] ",
            secrets=secrets,
        )
        gym_pid = gym.pid
        if on_spawn:
            on_spawn(gym_pid)
        deadline = time.monotonic() + ready_seconds
        next_detail = 0.0
        last_size = -1
        last_growth = time.monotonic()
        while time.monotonic() < deadline:
            if gym.poll() is not None:
                _wait_logged(gym)
                tail = _scrub(_tail(run_log), secrets)
                if on_log:
                    on_log(tail)
                raise DemoRunError(_gym_failed_message(tail), tail)
            if _http_ok(READY_URL, timeout=3):
                break
            size = run_log.stat().st_size if run_log.is_file() else 0
            now = time.monotonic()
            if size != last_size:
                last_size = size
                last_growth = now
            elif installed and now - last_growth >= LOG_STALL_SECONDS:
                tail = _scrub(_tail(run_log), secrets)
                if on_log:
                    on_log(tail)
                raise DemoRunError(
                    "NeMo Gym stopped printing and never became ready. "
                    + _ray_hint(tail),
                    tail,
                )
            if now >= next_detail:
                tail = _scrub(_tail(run_log), secrets)
                if on_log:
                    on_log(tail)
                line = _scrub(_last_line(run_log), secrets)
                if installed:
                    detail = "Waiting until NeMo Gym reports ready. The server environments are already installed."
                else:
                    detail = (
                        "Server environments are not in this image, so NeMo Gym is installing them. "
                        "That is slower than a prepared image."
                    )
                if line:
                    detail = f"{detail} Latest: {line}"
                on_step("gym", "running", detail)
                next_detail = now + 2
            time.sleep(1)
        else:
            tail = _scrub(_tail(run_log), secrets)
            if on_log:
                on_log(tail)
            raise DemoRunError(
                f"NeMo Gym did not become ready within {ready_seconds} seconds. " + _ray_hint(tail),
                tail,
            )
        on_step("gym", "done", "NeMo Gym is ready.")

        temperature = policy.get("DEMO_TEMPERATURE") or os.environ.get("DEMO_TEMPERATURE", "0") or "0"
        for item in plan:
            key = item["id"]
            extra = [f"+skills.path={item['path']}"] if item.get("path") else []
            on_step(key, "running", f"NeMo Gym is collecting {len(CASES)} rollouts for {item['label']}.")
            log_path = results / f"{key}.log"
            command = [
                *gym_cmd,
                "eval",
                "run",
                "--no-serve",
                "--agent",
                "ticketnow_desk_skills_agent",
                "--input",
                "resources_servers/ticketnow_desk/data/tasks.jsonl",
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
            completed = _popen_logged(
                command,
                cwd=root,
                env=_child_env(root, policy),
                logs=[log_path, run_log],
                prefix="[gym] ",
                secrets=secrets,
            )
            if _wait_logged(completed) != 0:
                tail = _scrub(_tail(log_path), secrets)
                raise DemoRunError(f"Scoring {key.replace('_', ' ')} failed.", tail)
            on_step(key, "done", f"{len(CASES)} rollouts scored.")

        on_step("report", "running", "Comparing the scored configurations.")
        label, model_name, host = _source_label(mode, policy)
        chosen = tuple((item["id"], item["label"]) for item in plan)
        write_report(
            results,
            results / "comparison.md",
            results / "trace.md",
            "offboard-friday",
            variants=chosen,
        )
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
            variants=chosen,
        )
        on_step("report", "done", "Comparison ready.")
        if on_log:
            on_log(_scrub(_tail(run_log), secrets))
        return view
    finally:
        _kill_process_group(gym_pid)
        _kill_process_group(mock_pid)


def _ray_hint(tail: str) -> str:
    lowered = tail.lower()
    if any(token in lowered for token in ("ray", "shm", "object store", "memory")):
        return (
            "Ray did not become ready. The log below is what Gym printed. "
            "Recorded sample does not start Ray."
        )
    return "The server log is below. Recorded sample does not start NeMo Gym."


def _gym_failed_message(tail: str) -> str:
    return "NeMo Gym stopped before the servers were ready. " + _ray_hint(tail)


def run_steps(mode: str, variants: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Checklist shown while a run is in progress. Recorded sample completes it at once."""
    plan = variants if variants is not None else list(run_plan())
    if mode == "recorded":
        steps = [
            {"id": "prepare", "label": "Prepare the tickets", "state": "done", "detail": "Using the tickets from the recorded run."},
            {"id": "model", "label": "Call a model", "state": "done", "detail": "No model was called. The recording used mock-it-lead."},
            {"id": "gym", "label": "Start NeMo Gym", "state": "done", "detail": "NeMo Gym already scored this recording."},
        ]
        for item in plan:
            steps.append(
                {
                    "id": item["id"],
                    "label": f"Score: {item['label']}",
                    "state": "done",
                    "detail": "Loaded from sample_run.",
                }
            )
        steps.append({"id": "report", "label": "Build the comparison", "state": "done", "detail": "Comparison ready."})
        return steps
    model_label = "Start the mock model" if mode == "mock" else "Check the live model"
    steps = [
        {"id": "prepare", "label": "Prepare the tickets", "state": "pending", "detail": ""},
        {"id": "model", "label": model_label, "state": "pending", "detail": ""},
        {"id": "gym", "label": "Start NeMo Gym", "state": "pending", "detail": ""},
    ]
    for item in plan:
        steps.append({"id": item["id"], "label": f"Score: {item['label']}", "state": "pending", "detail": ""})
    steps.append({"id": "report", "label": "Build the comparison", "state": "pending", "detail": ""})
    return steps
