"""Presenter-facing names for the TicketNow tickets.

The verifier still uses the codes in ``policy.py``. These strings are only
for the briefing page.
"""

from __future__ import annotations

from resources_servers.ticketnow_desk.policy import Decision


TITLES = {
    "github-access": "GitHub access",
    "mfa-new-phone": "MFA on a new phone",
    "vpn-down": "VPN cannot reach internal sites",
    "mailbox-full": "Mailbox full",
    "laptop-dead": "Laptop will not turn on",
    "vscode-install": "Install VS Code",
    "new-hire-monday": "New hire on Monday",
    "offboard-friday": "Offboard on Friday",
    "phishing-click": "Clicked a suspicious link",
    "stolen-laptop": "Laptop left in a rideshare",
    "mdm-enroll": "Phone will not enroll",
    "aged-escalation": "Escalate a three-day ticket",
}

TYPE_PLAIN = {
    "incident": "Incident",
    "request": "Request",
    "inquiry": "Inquiry",
}

CATEGORY_PLAIN = {
    "access": "Access and identity",
    "network": "Network",
    "email": "Email",
    "hardware": "Hardware",
    "software": "Software",
    "lifecycle": "Joiner or leaver",
    "security": "Security",
    "mobile": "Mobile",
    "status": "Status",
}

GROUP_PLAIN = {
    "identity-access": "Identity and access",
    "network-ops": "Network operations",
    "collaboration": "Collaboration",
    "endpoint-support": "Endpoint support",
    "application-support": "Application support",
    "lifecycle": "Lifecycle",
    "security-operations": "Security operations",
    "mobile-devices": "Mobile devices",
    "service-desk": "Service desk",
}

ACTION_PLAIN = {
    "manager_approval": "get manager approval",
    "disable_same_day": "disable accounts the same day",
    "collect_equipment": "collect equipment",
    "provision_accounts": "provision accounts",
    "provision_equipment": "provision a laptop",
    "reset_credentials": "reset credentials",
    "restore_service": "restore service",
    "dispatch_tech": "dispatch a technician",
    "fulfill_catalog": "fulfill from the catalog",
    "reset_enrollment": "reset device enrollment",
    "send_kb": "send the how-to article",
    "status_update": "send a status update and raise the priority",
    "isolate_session": "isolate the session",
    "remote_wipe": "wipe the device",
    "preserve_mailbox": "preserve the mailbox",
}


def ticket_title(case_id: str) -> str:
    return TITLES.get(case_id, case_id.replace("-", " "))


def outcome_line(decision: Decision) -> str:
    group = GROUP_PLAIN.get(decision.assignment_group, decision.assignment_group)
    kind = TYPE_PLAIN.get(decision.ticket_type, decision.ticket_type)
    actions = ", ".join(ACTION_PLAIN.get(code, code.replace("_", " ")) for code in decision.actions)
    sentence = actions[0].upper() + actions[1:] if actions else "No extra action"
    if not sentence.endswith("."):
        sentence += "."
    return f"{kind} · {decision.priority} · {group}. {sentence}"
