"""JSON view of a finished three-way TicketNow run.

The markdown report and this payload share one grader, so the briefing page
and ``results/comparison.md`` cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from demo.report import VARIANTS, _case_for, _grade, _index, _load
from demo.story import outcome_line, ticket_title
from resources_servers.ticketnow_desk.policy import CASES


def load_by_variant(results: Path) -> dict[str, dict[str, dict[str, Any]]]:
    return {key: _index(_load(results / f"{key}.jsonl")) for key, _label in VARIANTS}


def _plain_cell(procedure: float, decision: float) -> str:
    if procedure == 1.0 and decision == 1.0:
        return "Right outcome"
    if procedure == 1.0 and decision == 0.0:
        return "Looked it up, wrong outcome"
    if decision == 1.0:
        return "Right outcome, skipped a lookup"
    return "Wrong outcome"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(f"{sum(values) / len(values):.2f}")


def comparison_payload(by_variant: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    tickets = []
    means: dict[str, list[float]] = {key: [] for key, _label in VARIANTS}
    passes = {key: 0 for key, _label in VARIANTS}
    for case in CASES:
        cells = []
        for key, label in VARIANTS:
            row = by_variant[key].get(case["case_id"])
            if row is None:
                cells.append({"variant": key, "label": label, "missing": True})
                continue
            graded = _grade(row)
            gym_reward = row.get("reward")
            cell = {
                "variant": key,
                "label": label,
                "missing": False,
                "reward": graded.reward,
                "gym_reward": gym_reward if isinstance(gym_reward, (int, float)) else None,
                "procedure": graded.procedure,
                "decision": graded.decision,
                "passed": graded.decision == 1.0,
                "plain": _plain_cell(graded.procedure, graded.decision),
                "notes": graded.notes,
            }
            cells.append(cell)
            means[key].append(graded.reward)
            passes[key] += int(graded.decision == 1.0)
        tickets.append(
            {
                "case_id": case["case_id"],
                "ticket_id": case["ticket"]["ticket_id"],
                "title": ticket_title(case["case_id"]),
                "cells": cells,
            }
        )
    summary = []
    for key, label in VARIANTS:
        summary.append(
            {
                "variant": key,
                "label": label,
                "mean_reward": _mean(means[key]),
                "correct": passes[key],
                "total": len(CASES),
            }
        )
    return {"tickets": tickets, "summary": summary}


def _parsed(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None
    return None


def _arguments(raw: Any) -> dict[str, Any]:
    return _parsed(raw) or {}


def _excerpt(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _describe_call(name: str, args: dict[str, Any]) -> tuple[str, str, str]:
    """Return kind, title, and a sentence a non-engineer can read."""
    if name == "activate_skill":
        skill = args.get("name") or "a skill"
        return (
            "Skill",
            f"Opened {skill}",
            "Until this step the model had only the skill's name and one-line description. Opening it loads the playbook.",
        )
    if name == "read_skill_file":
        path = args.get("relative_path") or "a file"
        return (
            "Reference",
            f"Read {path}",
            "The playbook told the lead to open this file. The priority levels live here, not in the ticket.",
        )
    if name == "lookup_requester":
        return (
            "Tool",
            f"Looked up requester {args.get('requester_id') or ''}".strip(),
            "The employee record has employment status. The handoff does not.",
        )
    if name == "lookup_ticket":
        return (
            "Tool",
            f"Looked up ticket {args.get('ticket_id') or ''}".strip(),
            "The ticket record carries the intake tag, the category, and any security signal. The wording of the message is not that record.",
        )
    if name == "file_triage":
        priority = args.get("priority") or "a priority"
        group = args.get("assignment_group") or "a queue"
        kind = args.get("ticket_type") or "a type"
        return (
            "Decision",
            f"Filed {kind} {priority} to {group}",
            "One triage. The verifier grades this call: type, category, priority, assignment group, and actions.",
        )
    return ("Tool", name or "Tool call", "The lead called a tool.")


def _describe_return(name: str, output: Any) -> str:
    data = _parsed(output)
    if name == "lookup_requester" and data and "name" in data:
        return (
            f"{data.get('name')} · {data.get('employment') or 'unknown status'} · "
            f"{data.get('department') or 'unknown team'}"
        )
    if name == "lookup_ticket" and data and "ticket_id" in data:
        outage = " · site outage" if data.get("shared_outage") else ""
        return (
            f"{data.get('ticket_id')} · {data.get('intake_type')} · {data.get('category')} · "
            f"signal {data.get('security_signal') or 'none'} · open {data.get('hours_open')}h{outage}"
        )
    if name == "file_triage" and data:
        accepted = "accepted" if data.get("accepted") else "rejected"
        return f"Desk {accepted} the filing."
    if name == "read_skill_file" and data and isinstance(data.get("content"), str):
        return data["content"].strip()
    if name == "activate_skill" and data:
        return "Playbook loaded."
    if isinstance(output, str):
        return _excerpt(output)
    return _excerpt(json.dumps(output, ensure_ascii=False))


def _filed_triage(output: list[Any]) -> dict[str, Any] | None:
    filed = None
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        if item.get("name") != "file_triage":
            continue
        filed = _arguments(item.get("arguments"))
    return filed


def trace_payload(row: dict[str, Any]) -> dict[str, Any]:
    case = _case_for(row)
    graded = _grade(row)
    skills = row.get("skills_ref") or {}
    names = [item.get("name") for item in skills.get("skills") or [] if isinstance(item, dict)]
    output = (row.get("response") or {}).get("output") or []
    by_id: dict[str, dict[str, Any]] = {}
    for item in output:
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            call_id = item.get("call_id")
            if isinstance(call_id, str):
                by_id[call_id] = item
    steps: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "function_call_output":
            continue
        if kind != "function_call":
            if kind == "message" and item.get("role") == "assistant":
                content = item.get("content")
                if isinstance(content, list):
                    content = " ".join(
                        str(part.get("text") or "") for part in content if isinstance(part, dict)
                    )
                text = content if isinstance(content, str) else ""
                if text.strip():
                    steps.append(
                        {
                            "kind": "Reply",
                            "title": "Told the teammate the outcome",
                            "detail": "This is the lead's note back to the person who handed over the ticket.",
                            "excerpt": text.strip(),
                        }
                    )
            continue
        args = _arguments(item.get("arguments"))
        step_kind, title, detail = _describe_call(str(item.get("name") or ""), args)
        returned = by_id.get(item.get("call_id") or "")
        excerpt = ""
        if returned is not None:
            excerpt = _describe_return(str(item.get("name") or ""), returned.get("output"))
        step = {
            "kind": step_kind,
            "title": title,
            "detail": detail,
            "excerpt": excerpt,
        }
        if item.get("name") == "file_triage":
            step["filing"] = {
                "ticket_type": args.get("ticket_type"),
                "category": args.get("category"),
                "priority": args.get("priority"),
                "assignment_group": args.get("assignment_group"),
                "actions": args.get("actions") or "",
                "requester_message": args.get("requester_message") or "",
            }
        steps.append(step)

    filed = _filed_triage([item for item in output if isinstance(item, dict)])
    if graded.decision == 1.0 and graded.procedure == 1.0:
        verdict = "The filing matches the policy."
    elif graded.decision == 0.0 and graded.procedure == 1.0:
        verdict = "The lead looked up the requester and the ticket, then filed a different outcome than the policy."
    elif graded.decision == 1.0:
        verdict = "The decision matches the policy, but a required lookup was skipped."
    else:
        verdict = "The filing does not match the policy."
    gym_reward = row.get("reward")
    steps.append(
        {
            "kind": "Reward",
            "title": f"Verifier scored the ticket {graded.reward:.1f}",
            "detail": verdict,
            "excerpt": graded.notes,
            "score": {
                "procedure": graded.procedure,
                "decision": graded.decision,
                "reward": graded.reward,
                "gym_reward": gym_reward if isinstance(gym_reward, (int, float)) else None,
                "passed": graded.decision == 1.0,
                "expected_line": outcome_line(graded.expected),
                "expected_ticket_type": graded.expected.ticket_type,
                "expected_category": graded.expected.category,
                "expected_priority": graded.expected.priority,
                "expected_assignment_group": graded.expected.assignment_group,
                "expected_actions": ",".join(graded.expected.actions),
                "filed_ticket_type": None if filed is None else filed.get("ticket_type"),
                "filed_category": None if filed is None else filed.get("category"),
                "filed_priority": None if filed is None else filed.get("priority"),
                "filed_assignment_group": None if filed is None else filed.get("assignment_group"),
                "filed_actions": None if filed is None else filed.get("actions"),
            },
        }
    )
    return {
        "case_id": case["case_id"],
        "ticket_id": case["ticket"]["ticket_id"],
        "requester_id": case["requester"]["requester_id"],
        "title": ticket_title(case["case_id"]),
        "handoff": case["user"],
        "skills_path": skills.get("path") or "",
        "skills_hash": skills.get("hash") or "",
        "skills_loaded": [name for name in names if isinstance(name, str)],
        "steps": steps,
    }


def build_view(
    results: Path,
    *,
    kind: str,
    source_label: str,
    model: str,
    nemo_gym: str,
    endpoint_host: str = "",
) -> dict[str, Any]:
    by_variant = load_by_variant(results)
    traces: dict[str, dict[str, Any]] = {}
    for case in CASES:
        traces[case["case_id"]] = {}
        for key, _label in VARIANTS:
            row = by_variant[key].get(case["case_id"])
            if row is not None:
                traces[case["case_id"]][key] = trace_payload(row)
    rollout_model = ""
    first = next(iter(by_variant["full_skills"].values()), None)
    if first:
        recorded = (first.get("response") or {}).get("model")
        if isinstance(recorded, str):
            rollout_model = recorded
    return {
        "kind": kind,
        "live_model": kind == "live",
        "source_label": source_label,
        "model": model,
        "rollout_model": rollout_model,
        "nemo_gym": nemo_gym,
        "endpoint_host": endpoint_host,
        "variants": [{"id": key, "label": label} for key, label in VARIANTS],
        "comparison": comparison_payload(by_variant),
        "traces": traces,
    }


def load_sample_view(root: Path) -> dict[str, Any]:
    sample = root / "sample_run"
    manifest_path = sample / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("sample_run/manifest.json is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded_on = manifest.get("recorded_on") or "2026-11-12"
    model = manifest.get("model") or "mock-it-lead"
    nemo_gym = str(manifest.get("nemo_gym") or "0.7.0")
    endpoint = str(manifest.get("endpoint") or "")
    host = endpoint.split("://", 1)[-1].split("/", 1)[0] if endpoint else ""
    label = (
        f"Recorded sample, {recorded_on}. Model {model}. NeMo Gym {nemo_gym}. "
        "This is not a call to a live model."
    )
    return build_view(
        sample,
        kind="recorded",
        source_label=label,
        model=str(model),
        nemo_gym=nemo_gym,
        endpoint_host=host,
    )
