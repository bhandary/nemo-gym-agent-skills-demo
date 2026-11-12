"""Policy, skills, the mock lead, and the comparison report."""

from __future__ import annotations

import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from demo.mock_model import MODEL_NAME, Handler, choose_action, decide_from_skill_text
from demo.report import TRACE_CASE, write_report
from demo.ray_bootstrap import OBJECT_STORE_BYTES, constrain_ray_init, cpu_budget
from demo.runner import (
    LOG_STALL_SECONDS,
    LOG_TAIL_LINES,
    READY_WITHOUT_VENVS_SECONDS,
    READY_WITH_VENVS_SECONDS,
    clip_log,
    gym_command,
)
from demo.skill_sets import (
    SKILLS,
    SHARED_SKILLS,
    UnknownSkill,
    materialize,
    run_plan,
    selection_config,
    sync_without_priority_matrix,
)
from nemo_gym.skills import hash_skill_dir, load_skill_directory, parse_skill_md
from resources_servers.ticketnow_desk import policy
from responses_api_agents.desk_skills_agent.skills_runtime import (
    activate_skill,
    read_skill_file,
    render_catalog,
    render_no_skills,
    skill_tools,
    stage_request_skills,
)


ROOT = Path(__file__).resolve().parents[1]
SECRETS = (
    "identity-access",
    "network-ops",
    "endpoint-support",
    "application-support",
    "security-operations",
    "mobile-devices",
    "service-desk",
    "manager_approval",
    "disable_same_day",
    "collect_equipment",
    "provision_accounts",
    "provision_equipment",
    "reset_credentials",
    "restore_service",
    "dispatch_tech",
    "fulfill_catalog",
    "reset_enrollment",
    "send_kb",
    "status_update",
    "isolate_session",
    "remote_wipe",
    "preserve_mailbox",
    "phishing_click",
    "lost_or_stolen",
    "account_compromise",
    "lifecycle",
    "P1",
    "P2",
    "P3",
    "P4",
    "72",
)

EXPECTED = {
    "github-access": ("request", "access", "P4", "identity-access", ("manager_approval",)),
    "mfa-new-phone": ("incident", "access", "P3", "identity-access", ("reset_credentials",)),
    "vpn-down": ("incident", "network", "P2", "network-ops", ("restore_service",)),
    "mailbox-full": ("incident", "email", "P3", "collaboration", ("restore_service",)),
    "laptop-dead": ("incident", "hardware", "P3", "endpoint-support", ("dispatch_tech",)),
    "vscode-install": ("request", "software", "P4", "application-support", ("fulfill_catalog",)),
    "new-hire-monday": ("request", "lifecycle", "P3", "lifecycle", ("provision_accounts", "provision_equipment")),
    "offboard-friday": ("request", "lifecycle", "P2", "lifecycle", ("collect_equipment", "disable_same_day")),
    "phishing-click": ("incident", "security", "P1", "security-operations", ("isolate_session", "reset_credentials")),
    "stolen-laptop": ("incident", "security", "P1", "security-operations", ("remote_wipe", "reset_credentials")),
    "mdm-enroll": ("incident", "mobile", "P3", "mobile-devices", ("reset_enrollment",)),
    "aged-escalation": ("inquiry", "status", "P2", "service-desk", ("status_update",)),
}

PASSES_WITHOUT_MATRIX = {"phishing-click", "stolen-laptop"}


def test_policy_decisions_cover_the_desk() -> None:
    assert len(policy.CASES) == 12
    categories = {case["ticket"]["category"] for case in policy.CASES}
    assert categories == {
        "access",
        "network",
        "email",
        "hardware",
        "software",
        "lifecycle",
        "security",
        "mobile",
        "status",
    }
    intakes = {case["ticket"]["intake_type"] for case in policy.CASES}
    assert intakes == {"incident", "request", "inquiry"}
    for case in policy.CASES:
        got = policy.decide(case["requester"], case["ticket"])
        assert got.as_tuple() == EXPECTED[case["case_id"]]


def test_security_beats_offboarding_and_the_hour_threshold_is_inclusive() -> None:
    active = {"employment": "active"}
    young = policy.decide(
        active,
        {
            "security_signal": "none",
            "intake_type": "inquiry",
            "category": "status",
            "hours_open": policy.AGED_INQUIRY_HOURS - 1,
            "shared_outage": False,
        },
    )
    aged = policy.decide(
        active,
        {
            "security_signal": "none",
            "intake_type": "inquiry",
            "category": "status",
            "hours_open": policy.AGED_INQUIRY_HOURS,
            "shared_outage": False,
        },
    )
    assert (young.priority, young.actions) == ("P4", ("send_kb",))
    assert (aged.priority, aged.actions) == ("P2", ("status_update",))
    compromised = policy.decide(
        {"employment": "leaving"},
        {
            "security_signal": "account_compromise",
            "intake_type": "request",
            "category": "lifecycle",
            "hours_open": 1,
            "shared_outage": False,
        },
    )
    assert compromised.as_tuple() == (
        "incident",
        "security",
        "P1",
        "security-operations",
        ("isolate_session", "preserve_mailbox"),
    )


def test_score_weights_lookup_before_filing() -> None:
    case = policy.case_by_id("offboard-friday")
    perfect = policy.score_output(
        [
            {"type": "function_call", "name": "lookup_requester", "arguments": json.dumps({"requester_id": "EMP-18440"})},
            {"type": "function_call", "name": "lookup_ticket", "arguments": json.dumps({"ticket_id": "TKT-2408"})},
            {
                "type": "function_call",
                "name": "file_triage",
                "arguments": json.dumps(
                    {
                        "ticket_id": "TKT-2408",
                        "ticket_type": "Request",
                        "category": "lifecycle",
                        "priority": "p2",
                        "assignment_group": "lifecycle",
                        "actions": "disable_same_day, collect_equipment",
                    }
                ),
            },
        ],
        case,
    )
    assert perfect.reward == 1.0
    guessed = policy.score_output(
        [
            {"type": "function_call", "name": "lookup_requester", "arguments": json.dumps({"requester_id": "EMP-18440"})},
            {"type": "function_call", "name": "lookup_ticket", "arguments": json.dumps({"ticket_id": "TKT-2408"})},
            {
                "type": "function_call",
                "name": "file_triage",
                "arguments": json.dumps(
                    {
                        "ticket_id": "TKT-2408",
                        "ticket_type": "request",
                        "category": "lifecycle",
                        "priority": "P4",
                        "assignment_group": "lifecycle",
                        "actions": "collect_equipment,disable_same_day",
                    }
                ),
            },
        ],
        case,
    )
    assert guessed.procedure == 1.0
    assert guessed.decision == 0.0
    assert guessed.reward == 0.4
    assert "priority" in guessed.notes
    filed_first = policy.score_output(
        [
            {
                "type": "function_call",
                "name": "file_triage",
                "arguments": json.dumps(
                    {
                        "ticket_id": "TKT-2408",
                        "ticket_type": "request",
                        "category": "lifecycle",
                        "priority": "P2",
                        "assignment_group": "lifecycle",
                        "actions": "collect_equipment,disable_same_day",
                    }
                ),
            },
            {"type": "function_call", "name": "lookup_requester", "arguments": json.dumps({"requester_id": "EMP-18440"})},
            {"type": "function_call", "name": "lookup_ticket", "arguments": json.dumps({"ticket_id": "TKT-2408"})},
        ],
        case,
    )
    assert filed_first.procedure == 0.0
    assert filed_first.decision == 1.0
    assert filed_first.reward == 0.6


def test_tasks_do_not_contain_the_answer_key() -> None:
    rendered = policy.render_tasks_jsonl()
    committed = (ROOT / "resources_servers/ticketnow_desk/data/tasks.jsonl").read_text(encoding="utf-8")
    assert committed == rendered
    assert "Available skills" not in rendered
    assert "No operational skills are loaded" not in rendered
    for secret in SECRETS:
        assert secret not in rendered


def test_skill_directories_follow_the_spec_and_hide_the_codes() -> None:
    full = load_skill_directory("skills/full")
    assert len(full.hash) == 12
    assert full.hash == hash_skill_dir(ROOT / "skills/full")
    names = {item.name for item in full.skills}
    assert names == {
        "security-first-response",
        "ticket-classification",
        "access-request-policy",
        "priority-matrix",
    }
    for item in full.skills:
        assert item.version == "1.0.0"
        skill_dir = ROOT / "skills/full" / item.name
        assert parse_skill_md(skill_dir / "SKILL.md").name == skill_dir.name
        description = item.description or ""
        for secret in SECRETS:
            assert secret not in description
    matrix_body = (ROOT / "skills/full/priority-matrix/SKILL.md").read_text(encoding="utf-8").split("---", 2)[-1]
    assert "offboard_priority" not in matrix_body
    assert "references/priority-matrix.md" in matrix_body
    card = (ROOT / "skills/full/priority-matrix/references/priority-matrix.md").read_text(encoding="utf-8")
    assert f"offboard_priority: {policy.OFFBOARD_PRIORITY}" in card
    assert f"aged_inquiry_hours: {policy.AGED_INQUIRY_HOURS}" in card
    assert "phishing" in card.lower()
    assert "P1" in card
    security = (ROOT / "skills/full/security-first-response/SKILL.md").read_text(encoding="utf-8")
    assert f"p1_priority: {policy.P1_PRIORITY}" in security
    assert f"p1_group: {policy.SECURITY_GROUP}" in security
    assert "offboard_priority" not in security
    access = (ROOT / "skills/full/access-request-policy/SKILL.md").read_text(encoding="utf-8")
    assert "offboard_actions: collect_equipment,disable_same_day" in access
    assert "P2" not in access.split("---", 2)[-1]
    catalog = render_catalog(ROOT / "skills/full")
    assert catalog.startswith("Available skills")
    for secret in SECRETS:
        assert secret not in catalog
    assert "No operational skills are loaded for this run." in render_no_skills()
    assert "TicketNow" in render_no_skills()


def test_missing_skill_variant_is_the_full_set_without_the_priority_matrix() -> None:
    synced = sync_without_priority_matrix(ROOT)
    assert not (synced / "priority-matrix").exists()
    for name in SHARED_SKILLS:
        assert (synced / name / "SKILL.md").read_bytes() == (ROOT / "skills/full" / name / "SKILL.md").read_bytes()
    loaded = load_skill_directory("skills/without_priority_matrix")
    assert {item.name for item in loaded.skills} == set(SHARED_SKILLS)


def test_a_run_can_score_every_leave_one_out(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "skills" / "full", tmp_path / "skills" / "full")
    names = [name for name, _title in SKILLS]
    assert [item["id"] for item in run_plan()] == [
        "no_skills",
        "full_skills",
        "without_priority_matrix",
    ]
    full = selection_config(names)
    stamped = (tmp_path / "skills" / "full" / "priority-matrix" / "SKILL.md").read_bytes()
    assert materialize(tmp_path, full) == tmp_path / "skills" / "full"
    assert (tmp_path / "skills" / "full" / "priority-matrix" / "SKILL.md").read_bytes() == stamped
    without_access = selection_config([name for name in names if name != "access-request-policy"])
    assert without_access["id"] == "without_access_request_policy"
    assert without_access["label"] == "Without Access request policy"
    access_plan = run_plan([name for name in names if name != "access-request-policy"], compare_without_matrix=True)
    assert [(item["id"], item["label"]) for item in access_plan] == [
        ("no_skills", "No skills"),
        ("without_access_request_policy", "Without Access request policy"),
        ("selected", "Without the priority matrix"),
    ]
    assert access_plan[2]["skills"] == [
        "security-first-response",
        "ticket-classification",
    ]
    assert [item["id"] for item in run_plan([], compare_without_matrix=True)] == ["no_skills"]
    no_matrix = run_plan([name for name in names if name != "priority-matrix"], compare_without_matrix=True)
    assert [(item["id"], item["label"]) for item in no_matrix] == [
        ("no_skills", "No skills"),
        ("without_priority_matrix", "Without the priority matrix"),
    ]
    custom = run_plan(["security-first-response", "priority-matrix"], compare_without_matrix=True)
    assert [item["id"] for item in custom] == ["no_skills", "selected", "selection_without_matrix"]
    assert custom[1]["path"] == "skills/selected"
    assert custom[2]["path"] == "skills/selection_without_matrix"
    assert custom[1]["label"] == "Security first response, Priority matrix"
    assert custom[2]["label"] == "Without the priority matrix"
    dest = materialize(tmp_path, without_access)
    assert dest is not None
    assert not (dest / "access-request-policy").exists()
    assert (dest / "priority-matrix" / "SKILL.md").read_bytes() == stamped
    custom = selection_config(["security-first-response", "priority-matrix"])
    assert custom["id"] == "selected"
    assert custom["path"] == "skills/selected"
    assert gym_command(ROOT)[-2:] == ["-m", "demo.gym_main"]
    fresh = constrain_ray_init({})
    assert fresh["include_dashboard"] is False
    assert fresh["num_cpus"] == cpu_budget()
    assert 1 <= fresh["num_cpus"] <= 2
    assert fresh["object_store_memory"] == OBJECT_STORE_BYTES
    assert fresh["_plasma_directory"] == "/tmp"
    assert fresh["_temp_dir"] == "/tmp/ray"
    assert constrain_ray_init({"address": "127.0.0.1:1"}) == {"address": "127.0.0.1:1"}
    assert len(clip_log("\n".join(f"line {i}" for i in range(250))).splitlines()) == LOG_TAIL_LINES
    assert READY_WITH_VENVS_SECONDS == 180
    assert READY_WITHOUT_VENVS_SECONDS == 300
    assert LOG_STALL_SECONDS == 90
    with pytest.raises(UnknownSkill, match="not-a-playbook"):
        selection_config(["not-a-playbook"])


def test_staging_activation_and_path_traversal(tmp_path: Path) -> None:
    root, staged = stage_request_skills(str(ROOT / "skills/full"))
    try:
        activated = json.loads(activate_skill(staged, "priority-matrix"))
        assert "references/priority-matrix.md" in activated["files"]
        assert "offboard_priority" not in activated["instructions"]
        card = json.loads(read_skill_file(staged, "priority-matrix", "references/priority-matrix.md"))
        assert "aged_inquiry_hours: 72" in card["content"]
        escaped = json.loads(read_skill_file(staged, "priority-matrix", "../security-first-response/SKILL.md"))
        assert "error" in escaped
        absolute = json.loads(read_skill_file(staged, "priority-matrix", str(tmp_path / "priority-matrix.md")))
        assert "error" in absolute
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def _dispatch(skill_root: Path | None, name: str, arguments: dict) -> str:
    if skill_root is not None and name == "activate_skill":
        return activate_skill(skill_root, arguments["name"])
    if skill_root is not None and name == "read_skill_file":
        return read_skill_file(skill_root, arguments["name"], arguments["relative_path"])
    if name == "lookup_requester":
        return json.dumps(policy.lookup_requester_payload(arguments["requester_id"]))
    if name == "lookup_ticket":
        return json.dumps(policy.lookup_ticket_payload(arguments["ticket_id"]))
    if name == "file_triage":
        return json.dumps({"accepted": True, **arguments})
    return json.dumps({"error": f"unexpected tool {name}"})


def _run_case(case: dict, skill_root: Path | None) -> tuple[policy.Score, list]:
    banner = render_no_skills() if skill_root is None else render_catalog(skill_root)
    tools = list(policy.TOOLS)
    if skill_root is not None:
        tools.extend(skill_tools())
    messages = [
        {"role": "system", "content": f"{banner}\n\n{policy.PREAMBLE}"},
        {"role": "user", "content": case["user"]},
    ]
    output = []
    for _step in range(16):
        action = choose_action({"messages": messages, "tools": tools})
        message = action["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            output.append({"type": "message", "role": "assistant", "content": message["content"]})
            break
        call = calls[0]
        name = call["function"]["name"]
        arguments = json.loads(call["function"]["arguments"])
        result = _dispatch(skill_root, name, arguments)
        output.append(
            {"type": "function_call", "name": name, "arguments": call["function"]["arguments"], "call_id": call["id"]}
        )
        output.append({"type": "function_call_output", "call_id": call["id"], "output": result})
        messages.append(message)
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    else:
        pytest.fail("the mock did not finish the ticket")
    return policy.score_output(output, case), output


def test_mock_follows_only_the_skills_it_was_given() -> None:
    full_root = ROOT / "skills/full"
    missing_root = ROOT / "skills/without_priority_matrix"
    for case in policy.CASES:
        full, _trace = _run_case(case, full_root)
        assert full.decision == 1.0, case["case_id"]
        assert full.procedure == 1.0
        assert full.reward == 1.0
        none, _none_trace = _run_case(case, None)
        assert none.procedure == 1.0
        assert none.decision == 0.0
        assert none.reward == 0.4
        missing, _missing_trace = _run_case(case, missing_root)
        assert missing.procedure == 1.0
        should_pass = case["case_id"] in PASSES_WITHOUT_MATRIX
        assert missing.decision == (1.0 if should_pass else 0.0), case["case_id"]
    featured, trace = _run_case(policy.case_by_id(TRACE_CASE), full_root)
    names = [item["name"] for item in trace if item["type"] == "function_call"]
    assert names == [
        "activate_skill",
        "activate_skill",
        "activate_skill",
        "activate_skill",
        "read_skill_file",
        "lookup_requester",
        "lookup_ticket",
        "file_triage",
    ]
    assert featured.expected.priority == "P2"
    assert featured.expected.actions == ("collect_equipment", "disable_same_day")


def test_mock_does_not_call_the_company_policy_module() -> None:
    source = (ROOT / "demo/mock_model.py").read_text(encoding="utf-8")
    assert "resources_servers" not in source
    assert "policy.decide" not in source
    requester = policy.CASES[0]["requester"]
    ticket = policy.CASES[0]["ticket"]
    assert decide_from_skill_text(requester, ticket, {})["category"] == "general"


def test_report_table_and_trace(tmp_path: Path) -> None:
    rows = {key: [] for key in ("no_skills", "full_skills", "without_priority_matrix")}
    roots = {
        "no_skills": None,
        "full_skills": ROOT / "skills/full",
        "without_priority_matrix": ROOT / "skills/without_priority_matrix",
    }
    for key, skill_root in roots.items():
        for case in policy.CASES:
            graded, output = _run_case(case, skill_root)
            rows[key].append(
                {
                    "case_id": case["case_id"],
                    "reward": graded.reward,
                    "responses_create_params": {"input": [{"role": "user", "content": case["user"]}]},
                    "response": {
                        "output": output,
                        "metadata": {
                            "case_id": case["case_id"],
                            "procedure": f"{graded.procedure:.4f}",
                            "decision": f"{graded.decision:.4f}",
                        },
                    },
                    "skills_ref": {
                        "path": "skills/full" if skill_root else "",
                        "hash": "abc123abc123" if skill_root else "",
                        "skills": [{"name": "priority-matrix"}] if key == "full_skills" else [],
                    },
                }
            )
        target = tmp_path / f"{key}.jsonl"
        target.write_text("".join(json.dumps(row) + "\n" for row in rows[key]), encoding="utf-8")
    table = write_report(tmp_path, tmp_path / "comparison.md", tmp_path / "trace.md", TRACE_CASE)
    assert "12 / 12" in table
    assert "0 / 12" in table
    assert "2 / 12" in table
    assert "0.50" in table
    trace = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert "activate_skill" in trace
    assert "read_skill_file" in trace
    assert "disable_same_day" in trace


def test_mock_http_serves_chat_completions() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=5) as response:
            body = json.loads(response.read().decode())
        assert body["data"][0]["id"] == MODEL_NAME
        payload = json.dumps(
            {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": render_no_skills()},
                    {"role": "user", "content": policy.CASES[0]["user"]},
                ],
            }
        ).encode()
        request = Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            completion = json.loads(response.read().decode())
        call = completion["choices"][0]["message"]["tool_calls"][0]
        assert call["function"]["name"] == "lookup_requester"
        assert completion["choices"][0]["finish_reason"] == "tool_calls"
    finally:
        server.shutdown()
