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
    assert body["service"] == "ticketnow-it-desk"
    assert _client().get("/healthz").status_code == 200


def test_page_offers_run_demo() -> None:
    response = _client().get("/")
    assert response.status_code == 200
    assert "Run demo" in response.text
    assert "TicketNow" in response.text
    assert "IT service desk" in response.text
    assert "Presenter notes" not in response.text
    assert "five minutes" not in response.text.lower()
    page_js = (ROOT / "web/static/app.js").read_text(encoding="utf-8")
    assert "Presenter notes" not in page_js
    assert "talk_track" not in page_js
    assert "text/html" in response.headers["content-type"]
    assert "Employee request" in page_js
    assert "Skills loaded" in page_js
    assert "Agent decision" in page_js
    assert "Reward check" in page_js
    assert "Show technical details" in page_js
    assert "A run is already in progress. Showing it." in page_js
    assert "compare_without_matrix" in page_js


def test_briefing_lists_skills_and_tickets() -> None:
    body = _client().get("/api/briefing").json()
    assert [skill["name"] for skill in body["skills"]] == [
        "security-first-response",
        "ticket-classification",
        "access-request-policy",
        "priority-matrix",
    ]
    matrix = next(skill for skill in body["skills"] if skill["name"] == "priority-matrix")
    assert "P1" not in matrix["description"]
    assert "72" not in matrix["description"]
    card = next(doc for doc in matrix["documents"] if doc["label"] == "Priority matrix")
    assert "aged_inquiry_hours: 72" in card["markdown"]
    assert "P1" in card["markdown"]
    assert [ticket["ticket_id"] for ticket in body["tickets"]] == [
        "TKT-2401",
        "TKT-2402",
        "TKT-2403",
        "TKT-2404",
        "TKT-2405",
        "TKT-2406",
        "TKT-2407",
        "TKT-2408",
        "TKT-2409",
        "TKT-2410",
        "TKT-2411",
        "TKT-2412",
    ]
    phishing = next(ticket for ticket in body["tickets"] if ticket["ticket_id"] == "TKT-2409")
    assert "security signal" in phishing["glance"]
    assert "P1" in phishing["outcome"]
    inquiry = next(ticket for ticket in body["tickets"] if ticket["case_id"] == "aged-escalation")
    assert "Inquiry" in inquiry["outcome"]
    assert "talk_track" not in body
    assert body["modes"]["recorded"]["enabled"] is True
    assert [choice["name"] for choice in body["skill_choices"]] == [
        "security-first-response",
        "ticket-classification",
        "access-request-policy",
        "priority-matrix",
    ]
    assert [item["id"] for item in body["configurations"]] == [
        "no_skills",
        "full_skills",
        "without_security_first_response",
        "without_ticket_classification",
        "without_access_request_policy",
        "without_priority_matrix",
    ]
    assert body["configurations"][0]["baseline"] is True
    assert phishing["type_label"] == "Incident"
    assert phishing["category_label"]


def test_live_mode_stays_off_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLICY_API_KEY", raising=False)
    body = _client().get("/api/briefing").json()
    assert body["modes"]["live"]["enabled"] is False
    assert "POLICY_API_KEY" in body["modes"]["live"]["reason"]


def test_live_mode_enables_for_the_openai_desk_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLICY_API_KEY", "sk-live-secret-value")
    monkeypatch.setenv("POLICY_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("POLICY_MODEL_NAME", "gpt-4.1-mini")
    monkeypatch.setenv("POLICY_MODEL_TYPE", "openai_model")
    response = _client().get("/api/briefing")
    assert "sk-live-secret-value" not in response.text
    live = response.json()["modes"]["live"]
    assert live["enabled"] is True
    assert live["model_name"] == "gpt-4.1-mini"
    assert live["endpoint_host"] == "api.openai.com"
    assert live["model_type"] == "openai_model"
    assert "gpt-4.1-mini" in live["detail"]
    assert "api.openai.com" in live["detail"]
    assert "openai_model" in live["detail"]
    env = model_env("live")
    assert env["POLICY_MODEL_TYPE"] == "openai_model"
    assert env["POLICY_MODEL_NAME"] == "gpt-4.1-mini"
    assert env["POLICY_BASE_URL"] == "https://api.openai.com/v1"
    assert "sk-live-secret-value" in env["POLICY_API_KEY"]


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


def test_recorded_sample_matches_the_it_desk() -> None:
    view = load_sample_view(ROOT)
    assert view["kind"] == "recorded"
    assert view["live_model"] is False
    assert "not a call to a live model" in view["source_label"].lower()
    assert view["model"] == "mock-it-lead"
    summary = {item["variant"]: item for item in view["comparison"]["summary"]}
    assert summary["no_skills"]["mean_reward"] == pytest.approx(0.40)
    assert summary["full_skills"]["mean_reward"] == pytest.approx(1.00)
    assert summary["without_priority_matrix"]["mean_reward"] == pytest.approx(0.50)
    assert summary["no_skills"]["correct"] == 0
    assert summary["full_skills"]["correct"] == 12
    assert summary["without_priority_matrix"]["correct"] == 2
    offboard = next(row for row in view["comparison"]["tickets"] if row["case_id"] == "offboard-friday")
    rewards = {cell["variant"]: cell["reward"] for cell in offboard["cells"]}
    assert rewards["no_skills"] == pytest.approx(0.4)
    assert rewards["full_skills"] == pytest.approx(1.0)
    assert rewards["without_priority_matrix"] == pytest.approx(0.4)
    phishing = next(row for row in view["comparison"]["tickets"] if row["case_id"] == "phishing-click")
    phishing_passed = {cell["variant"]: cell["passed"] for cell in phishing["cells"]}
    assert phishing_passed["without_priority_matrix"] is True
    full = view["traces"]["offboard-friday"]["full_skills"]
    titles = [step["title"] for step in full["steps"]]
    assert "Opened security-first-response" in titles
    assert "Read references/priority-matrix.md" in titles
    assert any(step["kind"] == "Reward" and step["score"]["reward"] == pytest.approx(1.0) for step in full["steps"])
    bare = view["traces"]["offboard-friday"]["no_skills"]
    assert all(step["kind"] != "Skill" for step in bare["steps"])
    assert bare["steps"][-1]["score"]["reward"] == pytest.approx(0.4)
    checks = {row["label"]: row for row in full["steps"][-1]["score"]["checks"]}
    assert checks["Looked up the employee and the ticket before filing"]["passed"] is True
    assert checks["Priority"]["passed"] is True
    assert checks["Actions"]["expected"]
    missed = {row["label"]: row for row in bare["steps"][-1]["score"]["checks"]}
    assert missed["Priority"]["passed"] is False
    assert missed["Looked up the employee and the ticket before filing"]["passed"] is True


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
    from web.runs import RunState

    monkeypatch.setattr("web.runs.gym_available", lambda _root: (True, ""))
    app = create_app(ROOT)
    called = {"value": False}

    def spy(**_kwargs):
        called["value"] = True
        raise DemoRunError("should not run")

    monkeypatch.setattr("web.runs.execute_gym_run", spy)
    busy = RunState("mock")
    busy.id = "busy"
    app.state.runs._runs["busy"] = busy
    app.state.runs._order.append("busy")
    response = TestClient(app).post("/api/runs", json={"mode": "mock"})
    assert response.status_code == 409
    assert called["value"] is False
    detail = response.json()["detail"]
    assert detail["message"] == "A run is already in progress. Showing it."
    assert detail["run"]["id"] == "busy"
    assert detail["run"]["status"] == "running"


def test_mock_run_scores_the_checked_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def spy(**kwargs):
        captured["variants"] = kwargs["variants"]
        raise DemoRunError("stop before Gym")

    monkeypatch.setattr("web.runs.gym_available", lambda _root: (True, ""))
    monkeypatch.setattr("web.runs.execute_gym_run", spy)
    app = create_app(ROOT)
    app.state.runs.inline = True
    response = TestClient(app).post(
        "/api/runs",
        json={
            "mode": "mock",
            "skills": [
                "security-first-response",
                "ticket-classification",
                "access-request-policy",
                "priority-matrix",
            ],
            "compare_without_matrix": False,
        },
    )
    assert response.status_code == 200
    assert [item["id"] for item in captured["variants"]] == ["no_skills", "full_skills"]


def test_unknown_skill_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("web.runs.gym_available", lambda _root: (True, ""))
    response = _client().post("/api/runs", json={"mode": "mock", "skills": ["not-a-playbook"]})
    assert response.status_code == 400
    assert "Unknown skill" in response.text


def test_env_yaml_reuses_venvs_and_turns_reasoning_parser_off(tmp_path: Path) -> None:
    path = tmp_path / "env.yaml"
    write_env_yaml(
        path,
        {
            "POLICY_BASE_URL": "http://127.0.0.1:43117/v1",
            "POLICY_API_KEY": "mock",
            "POLICY_MODEL_NAME": "mock-it-lead",
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
    assert env["POLICY_MODEL_NAME"] == "mock-it-lead"
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
