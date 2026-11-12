"""The story the briefing page shows before anyone presses Run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from demo.runner import gym_available, venvs_ready
from demo.settings import model_settings
from demo.skill_sets import SKILLS, selection_config
from demo.story import CATEGORY_PLAIN, TYPE_PLAIN, outcome_line, ticket_title
from resources_servers.ticketnow_desk.policy import AGED_INQUIRY_HOURS, CASES, decide


SKILL_ORDER = (
    "security-first-response",
    "ticket-classification",
    "access-request-policy",
    "priority-matrix",
)
SKILL_TITLES = {
    "security-first-response": "Security first response",
    "ticket-classification": "Classify and route",
    "access-request-policy": "Access request policy",
    "priority-matrix": "Priority matrix",
}


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()
    end = text.find("\n---\n", 3)
    if end < 0:
        return {}, text.strip()
    loaded = yaml.safe_load(text[4:end]) or {}
    if not isinstance(loaded, dict):
        loaded = {}
    return loaded, text[end + 5 :].strip()


def _documents(skill_dir: Path) -> list[dict[str, str]]:
    documents = []
    files = [skill_dir / "SKILL.md"]
    references = skill_dir / "references"
    if references.is_dir():
        files.extend(sorted(path for path in references.rglob("*.md") if path.is_file()))
    for path in files:
        if not path.is_file():
            continue
        _meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        relative = path.relative_to(skill_dir).as_posix()
        if relative == "SKILL.md":
            label = "Playbook"
        elif relative.endswith("priority-matrix.md"):
            label = "Priority matrix"
        else:
            label = relative
        documents.append({"id": relative, "label": label, "markdown": body})
    return documents


def _skills(root: Path) -> list[dict[str, Any]]:
    base = root / "skills" / "full"
    skills = []
    for name in SKILL_ORDER:
        directory = base / name
        skill_md = directory / "SKILL.md"
        if not skill_md.is_file():
            continue
        meta, _body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
        version = ""
        metadata = meta.get("metadata")
        if isinstance(metadata, dict) and metadata.get("version") is not None:
            version = str(metadata["version"])
        skills.append(
            {
                "name": name,
                "title": SKILL_TITLES.get(name, name),
                "description": str(meta.get("description") or "").strip(),
                "version": version,
                "documents": _documents(directory),
            }
        )
    return skills


def _glance(case: dict[str, Any]) -> str:
    ticket = case["ticket"]
    requester = case["requester"]
    bits = [
        CATEGORY_PLAIN.get(ticket["category"], ticket["category"]),
        TYPE_PLAIN.get(ticket["intake_type"], ticket["intake_type"]).lower(),
    ]
    if ticket["security_signal"] != "none":
        bits.append("security signal on the ticket")
    if ticket["shared_outage"]:
        bits.append("site outage")
    if requester["employment"] == "leaving":
        bits.append("leaving")
    if requester["employment"] == "new_hire":
        bits.append("new hire")
    if int(ticket["hours_open"]) >= AGED_INQUIRY_HOURS:
        bits.append(f"open {ticket['hours_open']} hours")
    return " · ".join(bits)


def _tickets() -> list[dict[str, Any]]:
    tickets = []
    for case in CASES:
        decision = decide(case["requester"], case["ticket"])
        tickets.append(
            {
                "case_id": case["case_id"],
                "ticket_id": case["ticket"]["ticket_id"],
                "requester_id": case["requester"]["requester_id"],
                "title": ticket_title(case["case_id"]),
                "handoff": case["user"],
                "glance": _glance(case),
                "channel": case["ticket"]["channel"],
                "outcome": outcome_line(decision),
                "ticket_type": decision.ticket_type,
                "type_label": TYPE_PLAIN.get(decision.ticket_type, decision.ticket_type),
                "category": decision.category,
                "category_label": CATEGORY_PLAIN.get(decision.category, decision.category),
                "priority": decision.priority,
                "assignment_group": decision.assignment_group,
                "actions": list(decision.actions),
            }
        )
    return tickets


def briefing(root: Path) -> dict[str, Any]:
    settings = model_settings()
    gym_ok, gym_reason = gym_available(root)
    count = len(CASES)
    return {
        "title": "TicketNow",
        "kicker": "IT service desk",
        "lede": (
            f"{count} employee tickets. Four playbooks. The same grader every time. "
            "NeMo Gym scores a TicketNow IT service desk lead, and the only thing that changes "
            "is which operational skills the lead is allowed to open."
        ),
        "reward": (
            "Looking up the requester and the ticket is worth 0.4. "
            "Filing the type, category, priority, assignment group, and actions is worth 0.6. "
            "A lead who looks everything up and then guesses the priority still loses most of the point."
        ),
        "configurations": [
            {
                "id": item["id"],
                "label": item["label"],
                "skills": item["skills"],
                "baseline": item["id"] == "no_skills",
            }
            for item in (
                selection_config([]),
                selection_config([name for name, _title in SKILLS]),
                *(
                    selection_config([name for name, _title in SKILLS if name != omitted])
                    for omitted, _title in SKILLS
                ),
            )
        ],
        "skill_choices": [{"name": name, "title": title} for name, title in SKILLS],
        "skills": _skills(root),
        "tickets": _tickets(),
        "modes": {
            "recorded": {
                "enabled": (root / "sample_run" / "manifest.json").is_file(),
                "reason": "" if (root / "sample_run" / "manifest.json").is_file() else "sample_run is missing.",
                "detail": "Loads the finished run in sample_run. Nothing is executed. The model was mock-it-lead.",
            },
            "mock": {
                "enabled": gym_ok,
                "reason": gym_reason,
                "detail": (
                    f"Starts NeMo Gym and scores the {count} tickets against the local mock. This is not a live model."
                    if venvs_ready(root, "vllm_model")
                    else (
                        f"Starts NeMo Gym and scores the {count} tickets against the local mock. "
                        "This is not a live model. The first start installs server environments and can take several minutes."
                    )
                ),
            },
            "live": {
                "enabled": settings.live,
                "reason": settings.live_reason,
                "detail": (
                    f"Live model is on. NeMo Gym will call {settings.model_name} at {settings.endpoint_host} "
                    f"through {settings.model_type}."
                    if settings.live
                    else "Uses the endpoint configured on the server. The page never asks for a key."
                ),
                "model_name": settings.model_name if settings.live else "",
                "endpoint_host": settings.endpoint_host if settings.live else "",
                "model_type": settings.model_type if settings.live else "",
            },
        },
    }
