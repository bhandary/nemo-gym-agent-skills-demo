"""Policy, skills, the mock associate, and the comparison report."""

from __future__ import annotations

import json
import threading
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from demo.mock_model import Handler, choose_action, decide_from_skill_text
from demo.report import write_report
from demo.skill_sets import SHARED_SKILLS, sync_without_refund
from nemo_gym.skills import hash_skill_dir, load_skill_directory, parse_skill_md
from resources_servers.northwind_desk import policy
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
    "full_refund_unopened",
    "damage_window_partial",
    "goodwill_replacement",
    "deny_outside_window",
    "escalate_safety",
    "escalate_high_value",
    "unopened_full_refund_days",
    "opened_damage_refund_percent",
    "70",
    "200",
)


def test_policy_decisions_match_the_talk_track() -> None:
    expected = {
        "dented-kettle": ("damage_window_partial", 56.0, False),
        "unopened-jacket": ("full_refund_unopened", 120.0, False),
        "worn-shoes": ("goodwill_replacement", 0.0, False),
        "safety-blender": ("escalate_safety", 0.0, True),
        "high-value-tent": ("escalate_high_value", 0.0, True),
    }
    assert len(policy.CASES) == 5
    for case in policy.CASES:
        got = policy.decide(case["order"], case["ticket"])
        assert (got.disposition, got.refund_usd, got.escalate) == expected[case["case_id"]]


def test_half_up_rounding_and_score_weights() -> None:
    assert policy.money(Decimal("10.005")) == 10.01
    case = policy.CASES[0]
    perfect = policy.score_output(
        [
            {"type": "function_call", "name": "lookup_order", "arguments": json.dumps({"order_id": "NW-10482"})},
            {"type": "function_call", "name": "lookup_ticket", "arguments": json.dumps({"ticket_id": "T-441"})},
            {
                "type": "function_call",
                "name": "file_resolution",
                "arguments": json.dumps(
                    {
                        "ticket_id": "T-441",
                        "disposition": "damage_window_partial",
                        "refund_usd": 56,
                        "escalate": False,
                    }
                ),
            },
        ],
        case,
    )
    assert perfect.reward == 1.0
    guessed = policy.score_output(
        [
            {"type": "function_call", "name": "lookup_order", "arguments": json.dumps({"order_id": "NW-10482"})},
            {"type": "function_call", "name": "lookup_ticket", "arguments": json.dumps({"ticket_id": "T-441"})},
            {
                "type": "function_call",
                "name": "file_resolution",
                "arguments": json.dumps(
                    {"ticket_id": "T-441", "disposition": "refund", "refund_usd": 80, "escalate": False}
                ),
            },
        ],
        case,
    )
    assert guessed.procedure == 1.0
    assert guessed.decision == 0.0
    assert guessed.reward == 0.4
    filed_first = policy.score_output(
        [
            {
                "type": "function_call",
                "name": "file_resolution",
                "arguments": json.dumps(
                    {
                        "ticket_id": "T-441",
                        "disposition": "damage_window_partial",
                        "refund_usd": 56,
                        "escalate": False,
                    }
                ),
            },
            {"type": "function_call", "name": "lookup_order", "arguments": json.dumps({"order_id": "NW-10482"})},
            {"type": "function_call", "name": "lookup_ticket", "arguments": json.dumps({"ticket_id": "T-441"})},
        ],
        case,
    )
    assert filed_first.procedure == 0.0
    assert filed_first.decision == 1.0
    assert filed_first.reward == 0.6


def test_tasks_do_not_contain_the_answer_key() -> None:
    rendered = policy.render_tasks_jsonl()
    committed = (ROOT / "resources_servers/northwind_desk/data/tasks.jsonl").read_text(encoding="utf-8")
    assert committed == rendered
    assert "Available skills" not in rendered
    assert "No operational skills are loaded" not in rendered
    for secret in SECRETS:
        assert secret not in rendered


def test_skill_directories_follow_the_spec_and_hide_the_numbers() -> None:
    full = load_skill_directory("skills/full")
    assert len(full.hash) == 12
    assert full.hash == hash_skill_dir(ROOT / "skills/full")
    names = {item.name for item in full.skills}
    assert names == {"refund-policy", "escalation-playbook", "close-the-ticket"}
    for item in full.skills:
        assert item.version == "1.0.0"
        skill_dir = ROOT / "skills/full" / item.name
        assert parse_skill_md(skill_dir / "SKILL.md").name == skill_dir.name
        description = item.description or ""
        for secret in SECRETS:
            assert secret not in description
    refund_body = (ROOT / "skills/full/refund-policy/SKILL.md").read_text(encoding="utf-8").split("---", 2)[-1]
    assert "unopened_full_refund_days" not in refund_body
    assert "references/rate-card.md" in refund_body
    card = (ROOT / "skills/full/refund-policy/references/rate-card.md").read_text(encoding="utf-8")
    assert "unopened_full_refund_days: 30" in card
    assert "opened_damage_refund_percent: 70" in card
    catalog = render_catalog(ROOT / "skills/full")
    assert catalog.startswith("Available skills")
    for secret in SECRETS:
        assert secret not in catalog
    assert "No operational skills are loaded for this run." in render_no_skills()


def test_missing_skill_variant_is_the_full_set_without_refund_policy() -> None:
    synced = sync_without_refund(ROOT)
    assert not (synced / "refund-policy").exists()
    for name in SHARED_SKILLS:
        assert (synced / name / "SKILL.md").read_bytes() == (ROOT / "skills/full" / name / "SKILL.md").read_bytes()
    loaded = load_skill_directory("skills/without_refund_policy")
    assert {item.name for item in loaded.skills} == set(SHARED_SKILLS)


def test_staging_activation_and_path_traversal(tmp_path: Path) -> None:
    root, staged = stage_request_skills(str(ROOT / "skills/full"))
    try:
        activated = json.loads(activate_skill(staged, "refund-policy"))
        assert "references/rate-card.md" in activated["files"]
        assert "unopened_full_refund_days" not in activated["instructions"]
        card = json.loads(read_skill_file(staged, "refund-policy", "references/rate-card.md"))
        assert "unopened_full_refund_days: 30" in card["content"]
        escaped = json.loads(read_skill_file(staged, "refund-policy", "../escalation-playbook/SKILL.md"))
        assert "error" in escaped
        absolute = json.loads(read_skill_file(staged, "refund-policy", str(tmp_path / "rate-card.md")))
        assert "error" in absolute
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def _dispatch(skill_root: Path | None, name: str, arguments: dict) -> str:
    if skill_root is not None and name == "activate_skill":
        return activate_skill(skill_root, arguments["name"])
    if skill_root is not None and name == "read_skill_file":
        return read_skill_file(skill_root, arguments["name"], arguments["relative_path"])
    if name == "lookup_order":
        return json.dumps(policy.lookup_order_payload(arguments["order_id"]))
    if name == "lookup_ticket":
        return json.dumps(policy.lookup_ticket_payload(arguments["ticket_id"]))
    if name == "file_resolution":
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
    for _step in range(12):
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
    missing_root = ROOT / "skills/without_refund_policy"
    for case in policy.CASES:
        full, trace = _run_case(case, full_root)
        assert full.decision == 1.0
        assert full.procedure == 1.0
        assert full.reward == 1.0
        none, _none_trace = _run_case(case, None)
        assert none.procedure == 1.0
        assert none.decision == 0.0
        assert none.reward == 0.4
        missing, _missing_trace = _run_case(case, missing_root)
        assert missing.procedure == 1.0
        should_pass = case["case_id"] in {"safety-blender", "high-value-tent"}
        assert missing.decision == (1.0 if should_pass else 0.0)
    dented, trace = _run_case(policy.case_by_id("dented-kettle"), full_root)
    names = [item["name"] for item in trace if item["type"] == "function_call"]
    assert names[:4] == [
        "activate_skill",
        "activate_skill",
        "read_skill_file",
        "activate_skill",
    ]
    assert "lookup_order" in names and "file_resolution" in names
    assert dented.expected.disposition == "damage_window_partial"


def test_mock_does_not_call_the_company_policy_module() -> None:
    source = (ROOT / "demo/mock_model.py").read_text(encoding="utf-8")
    assert "resources_servers" not in source
    assert "policy.decide" not in source
    order = policy.CASES[0]["order"]
    ticket = policy.CASES[0]["ticket"]
    assert decide_from_skill_text(order, ticket, {}) == ("refund", 80.0, False)


def test_report_table_and_trace(tmp_path: Path) -> None:
    rows = {key: [] for key in ("no_skills", "full_skills", "without_refund_policy")}
    roots = {
        "no_skills": None,
        "full_skills": ROOT / "skills/full",
        "without_refund_policy": ROOT / "skills/without_refund_policy",
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
                        "skills": [{"name": "refund-policy"}] if key == "full_skills" else [],
                    },
                }
            )
        target = tmp_path / f"{key}.jsonl"
        target.write_text("".join(json.dumps(row) + "\n" for row in rows[key]), encoding="utf-8")
    table = write_report(tmp_path, tmp_path / "comparison.md", tmp_path / "trace.md", "dented-kettle")
    assert "5 / 5" in table
    assert "0 / 5" in table
    assert "2 / 5" in table
    trace = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert "activate_skill" in trace
    assert "read_skill_file" in trace
    assert "damage_window_partial" in trace


def test_mock_http_serves_chat_completions() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=5) as response:
            body = json.loads(response.read().decode())
        assert body["data"][0]["id"] == "mock-desk-associate"
        payload = json.dumps(
            {
                "model": "mock-desk-associate",
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
        assert call["function"]["name"] == "lookup_order"
        assert completion["choices"][0]["finish_reason"] == "tool_calls"
    finally:
        server.shutdown()
