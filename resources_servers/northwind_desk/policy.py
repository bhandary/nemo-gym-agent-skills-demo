"""Northwind Outfitters support policy, as code.

This module is the verifier's ground truth. The agent never imports it.
The Agent Skills under ``skills/`` teach the same rules in prose. A test
checks that the skill text and this module still agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


UNOPENED_FULL_REFUND_DAYS = 30
OPENED_DAMAGE_DAYS = 14
OPENED_DAMAGE_REFUND_PERCENT = 70
HIGH_VALUE_MERCHANDISE_USD = 200

PREAMBLE = (
    "You are a Northwind Outfitters support associate. A teammate handed you one "
    "customer ticket. Look up the order and the ticket, then file a single resolution. "
    "The tools return facts, not company policy. Follow any operational skills listed "
    "for this run before you decide."
)


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Decision:
    disposition: str
    refund_usd: float
    escalate: bool


def decide(order: dict[str, Any], ticket: dict[str, Any]) -> Decision:
    """Apply Northwind's rules. Escalation wins, then the refund rate card."""
    if ticket["safety_flag"]:
        return Decision("escalate_safety", 0.0, True)
    if float(order["merchandise_usd"]) > HIGH_VALUE_MERCHANDISE_USD:
        return Decision("escalate_high_value", 0.0, True)
    days = int(order["days_since_delivery"])
    if not order["opened"] and days <= UNOPENED_FULL_REFUND_DAYS:
        return Decision("full_refund_unopened", float(order["merchandise_usd"]), False)
    if order["opened"] and order["damage_in_transit"] and days <= OPENED_DAMAGE_DAYS:
        refund = money(
            Decimal(str(order["merchandise_usd"]))
            * Decimal(OPENED_DAMAGE_REFUND_PERCENT)
            / Decimal(100)
        )
        return Decision("damage_window_partial", refund, False)
    if order["customer_tier"] == "gold":
        return Decision("goodwill_replacement", 0.0, False)
    return Decision("deny_outside_window", 0.0, False)


CASES: list[dict[str, Any]] = [
    {
        "case_id": "dented-kettle",
        "user": (
            "Maya Chen wrote in on ticket T-441 about order NW-10482. "
            "She says the kettle arrived dented and she wants her money back. Handle the ticket."
        ),
        "order": {
            "order_id": "NW-10482",
            "item": "Cascade kettle",
            "merchandise_usd": 80.00,
            "shipping_usd": 8.00,
            "days_since_delivery": 9,
            "opened": True,
            "damage_in_transit": True,
            "customer_tier": "standard",
        },
        "ticket": {
            "ticket_id": "T-441",
            "safety_flag": False,
            "prior_contacts": 1,
            "channel": "email",
        },
    },
    {
        "case_id": "unopened-jacket",
        "user": (
            "Ticket T-442, order NW-11007. Jordan Lee says the jacket is still in the bag "
            "and wants to send it back. Handle the ticket."
        ),
        "order": {
            "order_id": "NW-11007",
            "item": "Harbor wool jacket",
            "merchandise_usd": 120.00,
            "shipping_usd": 0.00,
            "days_since_delivery": 20,
            "opened": False,
            "damage_in_transit": False,
            "customer_tier": "standard",
        },
        "ticket": {
            "ticket_id": "T-442",
            "safety_flag": False,
            "prior_contacts": 0,
            "channel": "chat",
        },
    },
    {
        "case_id": "worn-shoes",
        "user": (
            "Ticket T-443, order NW-11880. Sam Patel wore the shoes and is now asking for a refund. "
            "Handle the ticket."
        ),
        "order": {
            "order_id": "NW-11880",
            "item": "Trail runner",
            "merchandise_usd": 90.00,
            "shipping_usd": 6.50,
            "days_since_delivery": 40,
            "opened": True,
            "damage_in_transit": False,
            "customer_tier": "gold",
        },
        "ticket": {
            "ticket_id": "T-443",
            "safety_flag": False,
            "prior_contacts": 2,
            "channel": "phone",
        },
    },
    {
        "case_id": "safety-blender",
        "user": (
            "Ticket T-444, order NW-12110. The customer says the blender shocked them and they want "
            "a refund. Handle the ticket."
        ),
        "order": {
            "order_id": "NW-12110",
            "item": "Counter blender",
            "merchandise_usd": 80.00,
            "shipping_usd": 8.00,
            "days_since_delivery": 3,
            "opened": True,
            "damage_in_transit": True,
            "customer_tier": "standard",
        },
        "ticket": {
            "ticket_id": "T-444",
            "safety_flag": True,
            "prior_contacts": 0,
            "channel": "phone",
        },
    },
    {
        "case_id": "high-value-tent",
        "user": (
            "Ticket T-445, order NW-13050. Riley Nguyen wants to return a tent that is still sealed. "
            "Handle the ticket."
        ),
        "order": {
            "order_id": "NW-13050",
            "item": "Four-person tent",
            "merchandise_usd": 260.00,
            "shipping_usd": 18.00,
            "days_since_delivery": 10,
            "opened": False,
            "damage_in_transit": False,
            "customer_tier": "standard",
        },
        "ticket": {
            "ticket_id": "T-445",
            "safety_flag": False,
            "prior_contacts": 0,
            "channel": "email",
        },
    },
]


def case_by_id(case_id: str) -> dict[str, Any]:
    for case in CASES:
        if case["case_id"] == case_id:
            return case
    raise KeyError(case_id)


def lookup_order_payload(order_id: str) -> dict[str, Any]:
    for case in CASES:
        if case["order"]["order_id"] == order_id:
            return dict(case["order"])
    return {"error": f"No order named {order_id}."}


def lookup_ticket_payload(ticket_id: str) -> dict[str, Any]:
    for case in CASES:
        if case["ticket"]["ticket_id"] == ticket_id:
            return dict(case["ticket"])
    return {"error": f"No ticket named {ticket_id}."}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool(
        "lookup_order",
        "Look up an order. Returns facts only: price, shipping, age, whether it was opened, damage, and tier.",
        {"order_id": {"type": "string", "description": "Order id, for example NW-10482."}},
        ["order_id"],
    ),
    _tool(
        "lookup_ticket",
        "Look up a support ticket. Returns the channel, prior contacts, and whether safety review flagged it.",
        {"ticket_id": {"type": "string", "description": "Ticket id, for example T-441."}},
        ["ticket_id"],
    ),
    _tool(
        "file_resolution",
        (
            "Record the decision on the ticket. disposition is the company's code for this outcome. "
            "refund_usd is the merchandise refund as a number, or 0 when nothing is refunded. "
            "escalate is true only when a person must take the case."
        ),
        {
            "ticket_id": {"type": "string", "description": "Ticket being closed."},
            "disposition": {"type": "string", "description": "Exact company disposition code."},
            "refund_usd": {"type": "number", "description": "Merchandise refund in dollars."},
            "escalate": {"type": "boolean", "description": "True when a person must take the case."},
            "customer_message": {
                "type": "string",
                "description": "One or two plain sentences the customer can read.",
            },
        },
        ["ticket_id", "disposition", "refund_usd", "escalate", "customer_message"],
    ),
]


def render_tasks_jsonl() -> str:
    lines = []
    for case in CASES:
        row = {
            "case_id": case["case_id"],
            "responses_create_params": {
                "input": [
                    {"role": "developer", "content": PREAMBLE},
                    {"role": "user", "content": case["user"]},
                ],
                "parallel_tool_calls": False,
                "tools": TOOLS,
            },
        }
        lines.append(json.dumps(row, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def _as_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return item
    raise TypeError(f"Cannot read output item of type {type(item).__name__}")


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


@dataclass(frozen=True)
class Score:
    reward: float
    procedure: float
    decision: float
    notes: str
    expected: Decision


def score_output(output: list[Any], case: dict[str, Any]) -> Score:
    """Score a Responses API output list against one case.

    procedure is 1 when the agent looks up this order and this ticket before filing.
    decision is 1 when the last file_resolution matches the policy exactly.
    reward is 0.4 * procedure + 0.6 * decision. A busy agent that looks things up
    and then guesses the money still loses most of the point.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    for item in output:
        dumped = _as_dict(item)
        if dumped.get("type") != "function_call":
            continue
        calls.append((str(dumped.get("name") or ""), _arguments(dumped.get("arguments"))))

    expected = decide(case["order"], case["ticket"])
    file_at = [index for index, (name, _) in enumerate(calls) if name == "file_resolution"]
    notes: list[str] = []
    procedure = 0.0
    filed: dict[str, Any] = {}
    if file_at:
        before = calls[: file_at[-1]]
        saw_order = any(
            name == "lookup_order" and args.get("order_id") == case["order"]["order_id"]
            for name, args in before
        )
        saw_ticket = any(
            name == "lookup_ticket" and args.get("ticket_id") == case["ticket"]["ticket_id"]
            for name, args in before
        )
        procedure = 1.0 if saw_order and saw_ticket else 0.0
        filed = calls[file_at[-1]][1]
    else:
        notes.append("no file_resolution call")

    decision = 0.0
    if filed:
        got_disposition = str(filed.get("disposition", "")).strip()
        try:
            got_refund = float(filed["refund_usd"])
        except (KeyError, TypeError, ValueError):
            got_refund = None
        got_escalate = filed.get("escalate")
        disposition_ok = got_disposition == expected.disposition
        refund_ok = got_refund is not None and abs(got_refund - expected.refund_usd) < 0.001
        escalate_ok = got_escalate is expected.escalate
        decision = 1.0 if disposition_ok and refund_ok and escalate_ok else 0.0
        if not disposition_ok:
            notes.append(f"disposition {got_disposition or 'missing'} != {expected.disposition}")
        if not refund_ok:
            shown = "missing" if got_refund is None else f"{got_refund:.2f}"
            notes.append(f"refund {shown} != {expected.refund_usd:.2f}")
        if not escalate_ok:
            notes.append(f"escalate {got_escalate!r} != {expected.escalate}")
    if procedure < 1.0:
        notes.append("did not look up this order and ticket before filing")

    reward = round(0.4 * procedure + 0.6 * decision, 4)
    return Score(
        reward=reward,
        procedure=procedure,
        decision=decision,
        notes="; ".join(notes) if notes else "matches policy",
        expected=expected,
    )
