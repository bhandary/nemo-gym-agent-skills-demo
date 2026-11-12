"""One briefing run at a time.

Recorded sample finishes inside the request. Mock and live start NeMo Gym
on a background thread so the page can poll progress.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from demo.present import load_sample_view
from demo.runner import LOG_TAIL_LINES, DemoRunError, clip_log, execute_gym_run, gym_available, run_steps
from demo.settings import model_settings
from demo.skill_sets import UnknownSkill, run_plan


class RunBusy(Exception):
    def __init__(self, run: dict[str, Any]) -> None:
        super().__init__("A run is already in progress. Showing it.")
        self.run = run


class RunUnknown(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunState:
    def __init__(self, mode: str, variants: list[dict[str, Any]] | None = None) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.mode = mode
        self.status = "running"
        self.variants = variants if variants is not None else list(run_plan())
        self.steps = run_steps(mode, self.variants)
        self.error = ""
        self.log_tail = ""
        self.view: dict[str, Any] | None = None
        self.started_at = _now()
        self.finished_at = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "status": self.status,
            "steps": [dict(step) for step in self.steps],
            "error": self.error,
            "log_tail": self.log_tail,
            "view": self.view,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class RunManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.inline = False
        self._lock = threading.Lock()
        self._runs: dict[str, RunState] = {}
        self._order: list[str] = []
        self._groups: list[int] = []

    def start(
        self,
        mode: str,
        skill_names: list[str] | None = None,
        compare_without_matrix: bool = True,
    ) -> dict[str, Any]:
        self._reject_unavailable(mode)
        try:
            variants = (
                list(run_plan())
                if mode == "recorded"
                else list(run_plan(skill_names, compare_without_matrix=compare_without_matrix))
            )
        except UnknownSkill as exc:
            raise DemoRunError(str(exc)) from exc
        with self._lock:
            for run in self._runs.values():
                if run.status == "running":
                    raise RunBusy(run.to_dict())
            state = RunState(mode, variants)
            self._runs[state.id] = state
            self._order.append(state.id)
            self._trim()
        if self.inline or mode == "recorded":
            self._work(state)
        else:
            threading.Thread(target=self._work, args=(state,), daemon=True).start()
        return self.snapshot(state.id)

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                raise RunUnknown(run_id)
            return state.to_dict()

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._order:
                return None
            return self._runs[self._order[-1]].to_dict()

    def shutdown(self) -> None:
        from demo.runner import _kill_process_group

        with self._lock:
            pids = list(self._groups)
        for pid in pids:
            _kill_process_group(pid)

    def _track(self, pid: int) -> None:
        with self._lock:
            self._groups.append(pid)

    def _reject_unavailable(self, mode: str) -> None:
        if mode not in {"recorded", "mock", "live"}:
            raise DemoRunError("Choose recorded, mock, or live.")
        if mode == "recorded" and not (self.root / "sample_run" / "manifest.json").is_file():
            raise DemoRunError("sample_run is missing, so the recorded sample cannot load.")
        if mode == "mock":
            ok, reason = gym_available(self.root)
            if not ok:
                raise DemoRunError(reason)
        if mode == "live":
            settings = model_settings()
            if not settings.live:
                raise DemoRunError(settings.live_reason or "Live mode is not configured.")

    def _trim(self) -> None:
        while len(self._order) > 6:
            oldest = self._order[0]
            if self._runs[oldest].status == "running":
                return
            self._order.pop(0)
            self._runs.pop(oldest, None)

    def _work(self, state: RunState) -> None:
        try:
            if state.mode == "recorded":
                view = load_sample_view(self.root)
            else:
                view = execute_gym_run(
                    root=self.root,
                    mode=state.mode,
                    run_id=state.id,
                    on_step=lambda step_id, step_state, detail: self._mark(state, step_id, step_state, detail),
                    on_spawn=self._track,
                    on_log=lambda tail: self._log(state, tail),
                    variants=state.variants,
                )
            self._succeed(state, view)
        except DemoRunError as exc:
            self._fail(state, str(exc), exc.log_tail)
        except FileNotFoundError as exc:
            self._fail(state, str(exc), "")
        except Exception:
            self._fail(
                state,
                "The demo stopped before the comparison was ready.",
                traceback.format_exc()[-4000:],
            )

    def _log(self, state: RunState, tail: str) -> None:
        with self._lock:
            state.log_tail = clip_log(tail or "", LOG_TAIL_LINES)

    def _mark(self, state: RunState, step_id: str, step_state: str, detail: str) -> None:
        with self._lock:
            for step in state.steps:
                if step["id"] == step_id:
                    step["state"] = step_state
                    step["detail"] = detail
                    return

    def _succeed(self, state: RunState, view: dict[str, Any]) -> None:
        with self._lock:
            state.status = "succeeded"
            state.view = view
            state.finished_at = _now()
            state.error = ""

    def _fail(self, state: RunState, message: str, log_tail: str) -> None:
        with self._lock:
            if state.mode != "recorded" and "Recorded sample" not in message:
                message = (
                    message.rstrip()
                    + " Recorded sample does not start NeMo Gym. Switch to that mode to keep presenting."
                )
            state.status = "failed"
            state.error = message
            state.log_tail = clip_log(log_tail or "", LOG_TAIL_LINES)
            state.finished_at = _now()
            for step in state.steps:
                if step["state"] == "running":
                    step["state"] = "failed"
                    if not step["detail"]:
                        step["detail"] = "This step did not finish."
