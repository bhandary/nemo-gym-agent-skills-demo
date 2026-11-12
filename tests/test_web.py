"""Briefing page API, recorded sample, and the Gym runner's guards."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from demo.present import load_sample_view
from demo.runner import DemoRunError, execute_gym_run, model_env, write_env_yaml
from web.server import ROOT, create_app


def _client() -> TestClient:
    return TestClient(create_app(ROOT))


def test_health() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "northwind-desk"
    assert _client().get("/healthz").status_code == 200


def test_page_offers_run_demo() -> None:
    response = _client().get("/")
    assert response.status_code == 200
    assert "Run demo" in response.text
    assert "Northwind Outfitters" in response.text
    assert "text/html" in response.headers["content-type"]


def test_briefing_lists_skills_and_tickets() -> None:
    body = _client().get("/api/briefing").json()
    assert [skill["name"] for skill in body["skills"]] == [
        "escalation-playbook",
        "refund-policy",
        "close-the-ticket",
    ]
    refund = next(skill for skill in body["skills"] if skill["name"] == "refund-policy")
    assert "70" not in refund["description"]
    rate_card = next(doc for doc in refund["documents"] if doc["label"] == "Rate card")
    assert "opened_damage_refund_percent: 70" in rate_card["markdown"]
    assert [ticket["ticket_id"] for ticket in body["tickets"]] == [
        "T-441",
        "T-442",
        "T-443",
        "T-444",
        "T-445",
    ]
    safety = next(ticket for ticket in body["tickets"] if ticket["ticket_id"] == "T-444")
    assert "safety flag" in safety["glance"]
    assert "escalate" in safety["outcome"].lower() or "person" in safety["outcome"].lower()
    assert len(body["talk_track"]) >= 5
    assert body["modes"]["recorded"]["enabled"] is True


def test_live_mode_stays_off_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLICY_API_KEY", raising=False)
    body = _client().get("/api/briefing").json()
    assert body["modes"]["live"]["enabled"] is False
    assert "POLICY_API_KEY" in body["modes"]["live"]["reason"]


def test_live_mode_reports_the_model_without_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLICY_API_KEY", "sk-live-secret-value")
    monkeypatch.setenv("POLICY_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("POLICY_MODEL", "meta/llama-3.1-8b-instruct")
    monkeypatch.delenv("POLICY_MODEL_NAME", raising=False)
    response = _client().get("/api/briefing")
    assert "sk-live-secret-value" not in response.text
    live = response.json()["modes"]["live"]
    assert live["enabled"] is True
    assert live["model_name"] == "meta/llama-3.1-8b-instruct"
    assert live["endpoint_host"] == "integrate.api.nvidia.com"


def test_recorded_sample_matches_the_talk_track() -> None:
    view = load_sample_view(ROOT)
    assert view["kind"] == "recorded"
    assert view["live_model"] is False
    assert "not a call to a live model" in view["source_label"].lower()
    assert view["model"] == "mock-desk-associate"
    summary = {item["variant"]: item for item in view["comparison"]["summary"]}
    assert summary["no_skills"]["mean_reward"] == pytest.approx(0.40)
    assert summary["full_skills"]["mean_reward"] == pytest.approx(1.00)
    assert summary["without_refund_policy"]["mean_reward"] == pytest.approx(0.64)
    assert summary["no_skills"]["correct"] == 0
    assert summary["full_skills"]["correct"] == 5
    assert summary["without_refund_policy"]["correct"] == 2
    kettle = next(row for row in view["comparison"]["tickets"] if row["case_id"] == "dented-kettle")
    rewards = {cell["variant"]: cell["reward"] for cell in kettle["cells"]}
    assert rewards["no_skills"] == pytest.approx(0.4)
    assert rewards["full_skills"] == pytest.approx(1.0)
    assert rewards["without_refund_policy"] == pytest.approx(0.4)
    safety = next(row for row in view["comparison"]["tickets"] if row["case_id"] == "safety-blender")
    safety_rewards = {cell["variant"]: cell["passed"] for cell in safety["cells"]}
    assert safety_rewards["without_refund_policy"] is True
    full = view["traces"]["dented-kettle"]["full_skills"]
    titles = [step["title"] for step in full["steps"]]
    assert "Opened escalation-playbook" in titles
    assert "Read references/rate-card.md" in titles
    assert any(step["kind"] == "Reward" and step["score"]["reward"] == pytest.approx(1.0) for step in full["steps"])
    bare = view["traces"]["dented-kettle"]["no_skills"]
    assert all(step["kind"] != "Skill" for step in bare["steps"])
    assert bare["steps"][-1]["score"]["reward"] == pytest.approx(0.4)


def test_recorded_run_endpoint() -> None:
    response = _client().post("/api/runs", json={"mode": "recorded"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["view"]["kind"] == "recorded"
    assert body["view"]["comparison"]["summary"][1]["mean_reward"] == pytest.approx(1.00)
    assert "sk-live-secret-value" not in response.text


def test_unknown_mode_is_rejected() -> None:
    response = _client().post("/api/runs", json={"mode": "guess"})
    assert response.status_code == 422


def test_mock_failure_tells_the_presenter_to_use_the_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_kwargs):
        raise DemoRunError("Ray did not stay up in this container.", "object store memory")

    monkeypatch.setattr("web.runs.gym_available", lambda _root: (True, ""))
    monkeypatch.setattr("web.runs.execute_gym_run", boom)
    app = create_app(ROOT)
    app.state.runs.inline = True
    response = TestClient(app).post("/api/runs", json={"mode": "mock"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "Ray" in body["error"]
    assert "Recorded sample" in body["error"]
    assert "object store" in body["log_tail"]
    failed = [step for step in body["steps"] if step["state"] == "failed"]
    assert failed == [] or failed[0]["state"] == "failed"


def test_second_run_is_refused_while_one_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("web.runs.gym_available", lambda _root: (True, ""))
    app = create_app(ROOT)
    called = {"value": False}

    def spy(**_kwargs):
        called["value"] = True
        raise DemoRunError("should not run")

    monkeypatch.setattr("web.runs.execute_gym_run", spy)
    app.state.runs._runs["busy"] = type("Busy", (), {"status": "running"})()
    app.state.runs._order.append("busy")
    response = TestClient(app).post("/api/runs", json={"mode": "mock"})
    assert response.status_code == 409
    assert called["value"] is False


def test_env_yaml_reuses_venvs_and_turns_reasoning_parser_off(tmp_path: Path) -> None:
    path = tmp_path / "env.yaml"
    write_env_yaml(
        path,
        {
            "POLICY_BASE_URL": "http://127.0.0.1:43117/v1",
            "POLICY_API_KEY": "mock",
            "POLICY_MODEL_NAME": "mock-desk-associate",
            "POLICY_MODEL_TYPE": "vllm_model",
            "POLICY_REASONING_PARSER": "false",
        },
    )
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["skip_venv_if_present"] is True
    assert loaded["policy_api_key"] == "mock"
    model = loaded["policy_model"]["responses_api_models"]["vllm_model"]
    assert model["uses_reasoning_parser"] is False
    assert model["uses_interleaved_reasoning"] is False
    assert path.stat().st_mode & 0o777 == 0o600


def test_mock_env_does_not_copy_a_real_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLICY_API_KEY", "sk-super-secret-value")
    monkeypatch.setenv("POLICY_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("POLICY_MODEL_NAME", "should-not-leak")
    env = model_env("mock")
    assert env["POLICY_API_KEY"] == "mock"
    assert env["POLICY_MODEL_NAME"] == "mock-desk-associate"
    blob = " ".join(env.values())
    assert "sk-super-secret-value" not in blob
    assert "should-not-leak" not in blob


def test_live_run_refuses_before_starting_servers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("POLICY_API_KEY", raising=False)
    with pytest.raises(DemoRunError, match="POLICY_API_KEY"):
        execute_gym_run(root=tmp_path, mode="live", run_id="abc123", on_step=lambda *_args: None)


def test_gym_port_already_in_use_is_a_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("demo.runner.port_in_use", lambda _port: True)
    with pytest.raises(DemoRunError, match="11000"):
        execute_gym_run(root=tmp_path, mode="mock", run_id="abc123", on_step=lambda *_args: None)
