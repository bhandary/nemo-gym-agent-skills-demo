"""Presenter-facing names for the Northwind tickets and dispositions.

The verifier still uses the codes in ``policy.py``. These strings are only
for the briefing page.
"""

from __future__ import annotations

from resources_servers.northwind_desk.policy import Decision


TITLES = {
    "dented-kettle": "Dented kettle",
    "unopened-jacket": "Unopened jacket",
    "worn-shoes": "Worn shoes",
    "safety-blender": "Safety report",
    "high-value-tent": "High-value tent",
}

PLAIN_DISPOSITION = {
    "damage_window_partial": "Partial refund for transit damage",
    "full_refund_unopened": "Full merchandise refund, still sealed",
    "goodwill_replacement": "Goodwill replacement, no cash refund",
    "deny_outside_window": "Decline, outside both windows",
    "escalate_safety": "Hand to a person, safety flag",
    "escalate_high_value": "Hand to a person, merchandise over $200",
}

TALK_TRACK = (
    {
        "at": "0:00",
        "say": (
            "This page is NeMo Gym scoring a support associate. Same five tickets, "
            "same tools, same grader. The only change between the three columns is "
            "which playbooks the associate is allowed to open."
        ),
    },
    {
        "at": "0:40",
        "say": (
            "Open the three skills. The refund numbers are not in the handoff and "
            "not in the skill's opening description. They are in the rate card, "
            "which the playbook tells the associate to read."
        ),
    },
    {
        "at": "1:30",
        "say": (
            "Open the safety ticket. The handoff says the blender shocked the customer. "
            "The safety flag is a field on the ticket. The associate has to look it up. "
            "The tent is the same shape of surprise: the price is on the order, not in the note."
        ),
    },
    {
        "at": "2:20",
        "say": (
            "The table on screen is the recorded sample, so the room has numbers "
            "even if the network is unhappy. Hit Run demo to reload it. If you want "
            "NeMo Gym to score the tickets live in the room, switch to Mock model. "
            "That still is not NVIDIA or OpenAI. Live model is the real endpoint, "
            "and it is available only when the server already has a key."
        ),
    },
    {
        "at": "3:20",
        "say": (
            "Read the three averages. With no playbooks the associate still looks up "
            "the order and the ticket, so each ticket keeps 0.4, and every decision is wrong. "
            "With all three skills every decision matches and the reward is 1. "
            "Remove only the refund skill and the two escalation tickets still pass. "
            "The three ordinary refunds fail."
        ),
    },
    {
        "at": "4:20",
        "say": (
            "Open the dented-kettle trace on the full-skills run and step through it. "
            "The associate opens the escalation playbook, opens the refund skill, "
            "reads the rate card, looks up the order, and files a $56 partial refund. "
            "The verifier agrees. The skills hash is Gym's record of which files were on the run."
        ),
    },
    {
        "at": "4:50",
        "say": (
            "To change the policy, edit the skill and the verifier together. "
            "The tickets stay the same, so the comparison stays fair."
        ),
    },
)


def ticket_title(case_id: str) -> str:
    return TITLES.get(case_id, case_id.replace("-", " "))


def plain_disposition(code: str) -> str:
    return PLAIN_DISPOSITION.get(code, code.replace("_", " "))


def money(value: float) -> str:
    return f"${value:.2f}"


def outcome_line(decision: Decision) -> str:
    people = "Escalate to a person." if decision.escalate else "Do not escalate."
    if decision.refund_usd > 0:
        paid = f"Refund {money(decision.refund_usd)}."
    else:
        paid = "Refund $0.00."
    return f"{plain_disposition(decision.disposition)}. {paid} {people}"
