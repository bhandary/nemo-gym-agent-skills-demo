"""TicketNow IT service desk policy, as code.

This module is the verifier's ground truth. The agent never imports it.
The Agent Skills under ``skills/`` teach the same rules in prose. A test
checks that the skill text and this module still agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


P1_PRIORITY = "P1"
OFFBOARD_PRIORITY = "P2"
ONBOARD_PRIORITY = "P3"
OUTAGE_PRIORITY = "P2"
INCIDENT_PRIORITY = "P3"
REQUEST_PRIORITY = "P4"
INQUIRY_PRIORITY = "P4"
AGED_INQUIRY_PRIORITY = "P2"
AGED_INQUIRY_HOURS = 72

SECURITY_GROUP = "security-operations"
P1_SIGNALS = ("phishing_click", "lost_or_stolen", "account_compromise")

GROUPS = {
    "access": "identity-access",
    "network": "network-ops",
    "email": "collaboration",
    "hardware": "endpoint-support",
    "software": "application-support",
    "lifecycle": "lifecycle",
    "security": "security-operations",
    "mobile": "mobile-devices",
    "status": "service-desk",
}

SECURITY_ACTIONS = {
    "phishing_click": ("isolate_session", "reset_credentials"),
    "lost_or_stolen": ("remote_wipe", "reset_credentials"),
    "account_compromise": ("isolate_session", "preserve_mailbox"),
}

OFFBOARD_ACTIONS = ("collect_equipment", "disable_same_day")
ONBOARD_ACTIONS = ("provision_accounts", "provision_equipment")
ACCESS_REQUEST_ACTION = "manager_approval"
ACCESS_INCIDENT_ACTION = "reset_credentials"

INCIDENT_ACTIONS = {
    "network": "restore_service",
    "email": "restore_service",
    "hardware": "dispatch_tech",
    "mobile": "reset_enrollment",
    "software": "restore_service",
}
REQUEST_ACTIONS = {
    "software": "fulfill_catalog",
}
INQUIRY_ACTION = "send_kb"
AGED_INQUIRY_ACTION = "status_update"
GENERIC_REQUEST_ACTION = "fulfill_catalog"

PREAMBLE = (
    "You are a TicketNow IT service desk lead. A teammate handed you one employee "
    "ticket. Look up the requester and the ticket, then file a single triage. "
    "The tools return facts, not company policy. Follow any operational skills listed "
    "for this run before you decide."
)


@dataclass(frozen=True)
class Decision:
    ticket_type: str
    category: str
    priority: str
    assignment_group: str
    actions: tuple[str, ...]

    def as_tuple(self) -> tuple[str, str, str, str, tuple[str, ...]]:
        return (self.ticket_type, self.category, self.priority, self.assignment_group, self.actions)


def _actions(*codes: str) -> tuple[str, ...]:
    return tuple(sorted(code for code in codes if code))


def decide(requester: dict[str, Any], ticket: dict[str, Any]) -> Decision:
    """Apply TicketNow's rules. Security wins, then joiners and leavers, then the matrix."""
    signal = str(ticket.get("security_signal") or "none")
    if signal in P1_SIGNALS:
        return Decision(
            "incident",
            "security",
            P1_PRIORITY,
            SECURITY_GROUP,
            SECURITY_ACTIONS[signal],
        )

    employment = str(requester.get("employment") or "")
    category = str(ticket.get("category") or "")
    if category == "lifecycle" and employment in {"leaving", "left"}:
        return Decision("request", "lifecycle", OFFBOARD_PRIORITY, GROUPS["lifecycle"], OFFBOARD_ACTIONS)
    if category == "lifecycle" and employment == "new_hire":
        return Decision("request", "lifecycle", ONBOARD_PRIORITY, GROUPS["lifecycle"], ONBOARD_ACTIONS)

    intake = str(ticket.get("intake_type") or "")
    group = GROUPS[category]
    if category == "access" and intake == "request":
        return Decision(intake, category, REQUEST_PRIORITY, group, _actions(ACCESS_REQUEST_ACTION))
    if category == "access" and intake == "incident":
        return Decision(intake, category, INCIDENT_PRIORITY, group, _actions(ACCESS_INCIDENT_ACTION))
    if intake == "incident" and ticket.get("shared_outage"):
        return Decision(intake, category, OUTAGE_PRIORITY, group, _actions(INCIDENT_ACTIONS.get(category, "restore_service")))
    if intake == "incident":
        return Decision(intake, category, INCIDENT_PRIORITY, group, _actions(INCIDENT_ACTIONS.get(category, "restore_service")))
    if intake == "request":
        return Decision(
            intake,
            category,
            REQUEST_PRIORITY,
            group,
            _actions(REQUEST_ACTIONS.get(category, GENERIC_REQUEST_ACTION)),
        )
    if intake == "inquiry" and int(ticket.get("hours_open") or 0) >= AGED_INQUIRY_HOURS:
        return Decision(intake, category, AGED_INQUIRY_PRIORITY, group, _actions(AGED_INQUIRY_ACTION))
    if intake == "inquiry":
        return Decision(intake, category, INQUIRY_PRIORITY, group, _actions(INQUIRY_ACTION))
    raise ValueError(f"No rule for {intake} / {category}")


def _person(
    requester_id: str,
    name: str,
    department: str,
    manager: str,
    employment: str,
    location: str = "Austin",
) -> dict[str, Any]:
    return {
        "requester_id": requester_id,
        "name": name,
        "department": department,
        "manager": manager,
        "employment": employment,
        "location": location,
    }


def _ticket(
    ticket_id: str,
    intake_type: str,
    category: str,
    *,
    security_signal: str = "none",
    hours_open: int = 1,
    shared_outage: bool = False,
    channel: str = "chat",
    prior_contacts: int = 0,
) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "intake_type": intake_type,
        "category": category,
        "security_signal": security_signal,
        "hours_open": hours_open,
        "shared_outage": shared_outage,
        "channel": channel,
        "prior_contacts": prior_contacts,
    }


CASES: list[dict[str, Any]] = [
    {
        "case_id": "github-access",
        "user": (
            "Avery Cole wrote in on ticket TKT-2401 about requester EMP-18420. "
            "They need GitHub access for the platform team. Triage the ticket."
        ),
        "requester": _person("EMP-18420", "Avery Cole", "Platform", "Jordan Blake", "active"),
        "ticket": _ticket("TKT-2401", "request", "access", channel="chat", hours_open=1),
    },
    {
        "case_id": "mfa-new-phone",
        "user": (
            "Ticket TKT-2402, requester EMP-18421. Priya Shah got a new phone and can no "
            "longer finish sign-in. Triage the ticket."
        ),
        "requester": _person("EMP-18421", "Priya Shah", "Finance", "Robin Adeyemi", "active", "Chicago"),
        "ticket": _ticket("TKT-2402", "incident", "access", channel="phone", hours_open=2, prior_contacts=1),
    },
    {
        "case_id": "vpn-down",
        "user": (
            "Ticket TKT-2403, requester EMP-18422. Chris Nguyen says the VPN connects and "
            "then internal sites do not load. Triage the ticket."
        ),
        "requester": _person("EMP-18422", "Chris Nguyen", "Sales", "Skyler Moss", "active", "Denver"),
        "ticket": _ticket(
            "TKT-2403",
            "incident",
            "network",
            shared_outage=True,
            channel="chat",
            hours_open=1,
            prior_contacts=4,
        ),
    },
    {
        "case_id": "mailbox-full",
        "user": (
            "Ticket TKT-2404, requester EMP-18423. Dana Okonkwo says Outlook will not send "
            "because the mailbox is full. Triage the ticket."
        ),
        "requester": _person("EMP-18423", "Dana Okonkwo", "People", "Quinn Ibarra", "active"),
        "ticket": _ticket("TKT-2404", "incident", "email", channel="email", hours_open=4),
    },
    {
        "case_id": "laptop-dead",
        "user": (
            "Ticket TKT-2405, requester EMP-18424. Elena Vasquez says the laptop will not "
            "turn on before a customer meeting. Triage the ticket."
        ),
        "requester": _person("EMP-18424", "Elena Vasquez", "Customer office", "Noah Pell", "active", "Seattle"),
        "ticket": _ticket("TKT-2405", "incident", "hardware", channel="phone", hours_open=1),
    },
    {
        "case_id": "vscode-install",
        "user": (
            "Ticket TKT-2406, requester EMP-18425. Finn Alvarez is asking for Visual Studio "
            "Code on a company laptop. Triage the ticket."
        ),
        "requester": _person("EMP-18425", "Finn Alvarez", "Engineering", "Jordan Blake", "active"),
        "ticket": _ticket("TKT-2406", "request", "software", channel="chat", hours_open=6),
    },
    {
        "case_id": "new-hire-monday",
        "user": (
            "Ticket TKT-2407, requester EMP-18426. Harper Singh starts Monday and needs a "
            "laptop and accounts. Triage the ticket."
        ),
        "requester": _person("EMP-18426", "Harper Singh", "Engineering", "Jordan Blake", "new_hire"),
        "ticket": _ticket("TKT-2407", "request", "lifecycle", channel="email", hours_open=5),
    },
    {
        "case_id": "offboard-friday",
        "user": (
            "Ticket TKT-2408, requester EMP-18440. Morgan Lee's last day is Friday. Disable "
            "the accounts and collect the equipment. Triage the ticket."
        ),
        "requester": _person("EMP-18440", "Morgan Lee", "Finance", "Robin Adeyemi", "leaving", "Chicago"),
        "ticket": _ticket("TKT-2408", "request", "lifecycle", channel="email", hours_open=3),
    },
    {
        "case_id": "phishing-click",
        "user": (
            "Ticket TKT-2409, requester EMP-18428. Samir Haddad clicked a link in a mail "
            "that asked for a password. Triage the ticket."
        ),
        "requester": _person("EMP-18428", "Samir Haddad", "Legal", "Amina Shah", "active", "New York"),
        "ticket": _ticket(
            "TKT-2409",
            "incident",
            "security",
            security_signal="phishing_click",
            channel="phone",
            hours_open=0,
        ),
    },
    {
        "case_id": "stolen-laptop",
        "user": (
            "Ticket TKT-2410, requester EMP-18429. Riley Chen left a laptop in a rideshare "
            "and cannot find it. Triage the ticket."
        ),
        "requester": _person("EMP-18429", "Riley Chen", "Design", "Noah Pell", "active", "Seattle"),
        "ticket": _ticket(
            "TKT-2410",
            "incident",
            "security",
            security_signal="lost_or_stolen",
            channel="phone",
            hours_open=1,
        ),
    },
    {
        "case_id": "mdm-enroll",
        "user": (
            "Ticket TKT-2411, requester EMP-18430. The company phone for Quinn Brooks will "
            "not enroll in management. Triage the ticket."
        ),
        "requester": _person("EMP-18430", "Quinn Brooks", "Field", "Skyler Moss", "active", "Denver"),
        "ticket": _ticket("TKT-2411", "incident", "mobile", channel="chat", hours_open=2),
    },
    {
        "case_id": "aged-escalation",
        "user": (
            "Ticket TKT-2412, requester EMP-18431. Alex Kim wants their open ticket escalated "
            "and says it has been sitting for three days. Triage the ticket."
        ),
        "requester": _person("EMP-18431", "Alex Kim", "Operations", "Quinn Ibarra", "active"),
        "ticket": _ticket("TKT-2412", "inquiry", "status", channel="email", hours_open=80, prior_contacts=3),
    },
]


def case_by_id(case_id: str) -> dict[str, Any]:
    for case in CASES:
        if case["case_id"] == case_id:
            return case
    raise KeyError(case_id)


def lookup_requester_payload(requester_id: str) -> dict[str, Any]:
    for case in CASES:
        if case["requester"]["requester_id"] == requester_id:
            return dict(case["requester"])
    return {"error": f"No requester named {requester_id}."}


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
        "lookup_requester",
        "Look up an employee. Returns facts only: department, manager, employment, and location.",
        {"requester_id": {"type": "string", "description": "Requester id, for example EMP-18420."}},
        ["requester_id"],
    ),
    _tool(
        "lookup_ticket",
        (
            "Look up an IT ticket. Returns the intake tag, category, security signal, "
            "how long it has been open, whether monitoring sees a shared outage, the channel, "
            "and prior contacts."
        ),
        {"ticket_id": {"type": "string", "description": "Ticket id, for example TKT-2401."}},
        ["ticket_id"],
    ),
    _tool(
        "file_triage",
        (
            "Record one triage on the ticket. ticket_type, category, priority, and "
            "assignment_group are the company's codes for this outcome. actions is a "
            "comma-separated list of action codes with no spaces. requester_message is "
            "one or two plain sentences the employee can read."
        ),
        {
            "ticket_id": {"type": "string", "description": "Ticket being triaged."},
            "ticket_type": {"type": "string", "description": "Intake class for this ticket."},
            "category": {"type": "string", "description": "Desk category for this ticket."},
            "priority": {"type": "string", "description": "Priority code from policy."},
            "assignment_group": {"type": "string", "description": "Queue that owns the ticket."},
            "actions": {"type": "string", "description": "Comma-separated action codes, no spaces."},
            "requester_message": {
                "type": "string",
                "description": "One or two plain sentences the employee can read.",
            },
        },
        [
            "ticket_id",
            "ticket_type",
            "category",
            "priority",
            "assignment_group",
            "actions",
            "requester_message",
        ],
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


def normalize_actions(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        parts = [str(part) for part in value]
    else:
        parts = str(value or "").split(",")
    return tuple(sorted(part.strip().casefold() for part in parts if part.strip()))


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


@dataclass(frozen=True)
class Score:
    reward: float
    procedure: float
    decision: float
    notes: str
    expected: Decision


def score_output(output: list[Any], case: dict[str, Any]) -> Score:
    """Score a Responses API output list against one case.

    procedure is 1 when the agent looks up this requester and this ticket before filing.
    decision is 1 when the last file_triage matches type, category, priority, group, and actions.
    reward is 0.4 * procedure + 0.6 * decision. A lead who looks things up and then
    guesses the priority still loses most of the point.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    for item in output:
        dumped = _as_dict(item)
        if dumped.get("type") != "function_call":
            continue
        calls.append((str(dumped.get("name") or ""), _arguments(dumped.get("arguments"))))

    expected = decide(case["requester"], case["ticket"])
    file_at = [index for index, (name, _) in enumerate(calls) if name == "file_triage"]
    notes: list[str] = []
    procedure = 0.0
    filed: dict[str, Any] = {}
    if file_at:
        before = calls[: file_at[-1]]
        saw_requester = any(
            name == "lookup_requester" and args.get("requester_id") == case["requester"]["requester_id"]
            for name, args in before
        )
        saw_ticket = any(
            name == "lookup_ticket" and args.get("ticket_id") == case["ticket"]["ticket_id"]
            for name, args in before
        )
        procedure = 1.0 if saw_requester and saw_ticket else 0.0
        filed = calls[file_at[-1]][1]
    else:
        notes.append("no file_triage call")

    decision = 0.0
    if filed:
        got_type = _norm(filed.get("ticket_type"))
        got_category = _norm(filed.get("category"))
        got_priority = _norm(filed.get("priority"))
        got_group = _norm(filed.get("assignment_group"))
        got_actions = normalize_actions(filed.get("actions"))
        got_ticket = str(filed.get("ticket_id") or "").strip()
        type_ok = got_type == expected.ticket_type.casefold()
        category_ok = got_category == expected.category.casefold()
        priority_ok = got_priority == expected.priority.casefold()
        group_ok = got_group == expected.assignment_group.casefold()
        actions_ok = got_actions == expected.actions
        ticket_ok = got_ticket == case["ticket"]["ticket_id"]
        decision = 1.0 if type_ok and category_ok and priority_ok and group_ok and actions_ok and ticket_ok else 0.0
        if not ticket_ok:
            notes.append(f"ticket_id {got_ticket or 'missing'} != {case['ticket']['ticket_id']}")
        if not type_ok:
            notes.append(f"ticket_type {got_type or 'missing'} != {expected.ticket_type}")
        if not category_ok:
            notes.append(f"category {got_category or 'missing'} != {expected.category}")
        if not priority_ok:
            notes.append(f"priority {got_priority or 'missing'} != {expected.priority}")
        if not group_ok:
            notes.append(f"assignment_group {got_group or 'missing'} != {expected.assignment_group}")
        if not actions_ok:
            shown = ",".join(got_actions) if got_actions else "missing"
            notes.append(f"actions {shown} != {','.join(expected.actions)}")
    if procedure < 1.0:
        notes.append("did not look up this requester and ticket before filing")

    reward = round(0.4 * procedure + 0.6 * decision, 4)
    return Score(
        reward=reward,
        procedure=procedure,
        decision=decision,
        notes="; ".join(notes) if notes else "matches policy",
        expected=expected,
    )
