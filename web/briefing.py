"""The story the briefing page shows before anyone presses Run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from demo.runner import gym_available
from demo.settings import model_settings
from demo.story import TALK_TRACK, outcome_line, ticket_title
from resources_servers.northwind_desk.policy import CASES, decide


SKILL_ORDER = ("escalation-playbook", "refund-policy", "close-the-ticket")
SKILL_TITLES = {
    "escalation-playbook": "Escalation playbook",
    "refund-policy": "Refund policy",
    "close-the-ticket": "Close the ticket",
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
        label = "Playbook" if relative == "SKILL.md" else "Rate card" if relative.endswith("rate-card.md") else relative
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
    order = case["order"]
    bits = [
        order["item"],
        f"day {order['days_since_delivery']}",
        "sealed" if not order["opened"] else "opened",
    ]
    if order["damage_in_transit"]:
        bits.append("transit damage")
    if case["ticket"]["safety_flag"]:
        bits.append("safety flag")
    if float(order["merchandise_usd"]) > 200:
        bits.append(f"${float(order['merchandise_usd']):.0f} merchandise")
    elif order["customer_tier"] == "gold":
        bits.append("gold customer")
    return " · ".join(bits)


def _tickets() -> list[dict[str, Any]]:
    tickets = []
    for case in CASES:
        decision = decide(case["order"], case["ticket"])
        tickets.append(
            {
                "case_id": case["case_id"],
                "ticket_id": case["ticket"]["ticket_id"],
                "order_id": case["order"]["order_id"],
                "title": ticket_title(case["case_id"]),
                "handoff": case["user"],
                "glance": _glance(case),
                "channel": case["ticket"]["channel"],
                "outcome": outcome_line(decision),
                "disposition": decision.disposition,
                "refund_usd": decision.refund_usd,
                "escalate": decision.escalate,
            }
        )
    return tickets


def briefing(root: Path) -> dict[str, Any]:
    settings = model_settings()
    gym_ok, gym_reason = gym_available(root)
    return {
        "title": "Northwind Outfitters",
        "kicker": "Support desk briefing",
        "lede": (
            "Five customer tickets. Three playbooks. The same grader every time. "
            "NeMo Gym scores a support associate, and the only thing that changes "
            "is which operational skills the associate is allowed to open."
        ),
        "reward": (
            "Looking up the order and the ticket is worth 0.4. "
            "Filing the policy's decision is worth 0.6. "
            "An associate who looks everything up and then guesses the refund still loses most of the point."
        ),
        "configurations": [
            {"id": "no_skills", "label": "No skills", "detail": "The associate sees the tools and the handoff only."},
            {"id": "full_skills", "label": "Full skills", "detail": "Escalation, refund policy, and how to close the ticket."},
            {
                "id": "without_refund_policy",
                "label": "Refund skill removed",
                "detail": "Escalation and closing remain. The rate card is gone.",
            },
        ],
        "skills": _skills(root),
        "tickets": _tickets(),
        "talk_track": list(TALK_TRACK),
        "modes": {
            "recorded": {
                "enabled": (root / "sample_run" / "manifest.json").is_file(),
                "reason": "" if (root / "sample_run" / "manifest.json").is_file() else "sample_run is missing.",
                "detail": "Loads the finished run in sample_run. Nothing is executed. The model was mock-desk-associate.",
            },
            "mock": {
                "enabled": gym_ok,
                "reason": gym_reason,
                "detail": (
                    "Starts NeMo Gym and scores the five tickets three times against the local mock. "
                    "This is not a live model. The first start in a fresh checkout can take several minutes."
                ),
            },
            "live": {
                "enabled": settings.live,
                "reason": settings.live_reason,
                "detail": (
                    f"Starts NeMo Gym against {settings.model_name} at {settings.endpoint_host}."
                    if settings.live
                    else "Uses the endpoint configured on the server. The page never asks for a key."
                ),
                "model_name": settings.model_name if settings.live else "",
                "endpoint_host": settings.endpoint_host if settings.live else "",
            },
        },
    }
