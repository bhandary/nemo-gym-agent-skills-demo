"""Deterministic stand-in for an OpenAI-compatible chat model.

This is not a language model. It follows the skill text that is actually in
the conversation. If the priority matrix was never read, ordinary tickets get
the wrong priority. If the security playbook was never loaded, phishing and
lost-laptop tickets miss the priority-one short-circuit too.

NeMo Gym's ``vllm_model`` server translates the Responses API to
``POST {base_url}/chat/completions``. This server speaks that dialect.
``openai_model`` is the live adapter and is not used here.
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MODEL_NAME = "mock-it-lead"
DEFAULT_PORT = 43117

_KEY_RE = re.compile(r"(?m)^([a-z][a-z0-9_]*):\s*(\S+)\s*$")
_CATALOG_RE = re.compile(r"(?m)^- ([a-z0-9-]+): ")
_REQUESTER_RE = re.compile(r"EMP-\d+")
_TICKET_RE = re.compile(r"TKT-\d+")

SKILL_ORDER = (
    "security-first-response",
    "ticket-classification",
    "access-request-policy",
    "priority-matrix",
)

WRONG = {
    "ticket_type": "request",
    "category": "general",
    "priority": "P3",
    "assignment_group": "service-desk",
    "actions": "acknowledge",
}


def text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        return "\n".join(parts)
    return str(content)


def _loads(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_name(call: dict[str, Any]) -> str:
    function = call.get("function") or {}
    return str(function.get("name") or call.get("name") or "")


def _tool_arguments(call: dict[str, Any]) -> dict[str, Any]:
    function = call.get("function") or {}
    raw = function.get("arguments") if function else call.get("arguments")
    if raw is None:
        raw = call.get("arguments")
    return _loads(raw)


def walk(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Pull catalog names, tool results, and parsed policy lines out of a chat."""
    prose: list[str] = []
    calls: list[dict[str, Any]] = []
    results: dict[str, str] = {}
    for message in messages:
        role = message.get("role")
        if role == "tool":
            results[str(message.get("tool_call_id") or "")] = text_of(message.get("content"))
            continue
        if role == "assistant":
            for call in message.get("tool_calls") or []:
                calls.append(call)
            prose.append(text_of(message.get("content")))
            continue
        prose.append(text_of(message.get("content")))

    catalog = _CATALOG_RE.findall("\n".join(prose))
    completed: list[tuple[str, dict[str, Any], str]] = []
    facts: dict[str, str] = {}
    requester: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None
    filed = False
    for call in calls:
        name = _tool_name(call)
        arguments = _tool_arguments(call)
        output = results.get(str(call.get("id") or ""), "")
        completed.append((name, arguments, output))
        payload = _loads(output)
        blobs = [output]
        if isinstance(payload.get("instructions"), str):
            blobs.append(payload["instructions"])
        if isinstance(payload.get("content"), str):
            blobs.append(payload["content"])
        for blob in blobs:
            for match in _KEY_RE.finditer(blob):
                facts[match.group(1)] = match.group(2)
        if name == "lookup_requester" and "requester_id" in payload:
            requester = payload
        if name == "lookup_ticket" and "ticket_id" in payload and "intake_type" in payload:
            ticket = payload
        if name == "file_triage" and "error" not in payload:
            filed = True
    return {
        "catalog": catalog,
        "completed": completed,
        "facts": facts,
        "requester": requester,
        "ticket": ticket,
        "filed": filed,
        "prose": "\n".join(prose),
    }


def _did(state: dict[str, Any], tool_name: str, **expected: str) -> bool:
    for found_name, arguments, output in state["completed"]:
        if found_name != tool_name:
            continue
        if "error" in _loads(output):
            continue
        if all(str(arguments.get(key)) == value for key, value in expected.items()):
            return True
    return False


def _csv_set(facts: dict[str, str], key: str) -> set[str]:
    return {part for part in facts.get(key, "").split(",") if part}


def _actions_text(requester: dict[str, Any], ticket: dict[str, Any], facts: dict[str, str]) -> str:
    employment = str(requester.get("employment") or "")
    category = str(ticket.get("category") or "")
    intake = str(ticket.get("intake_type") or "")
    if category == "lifecycle" and employment in _csv_set(facts, "offboard_employment") and "offboard_actions" in facts:
        return facts["offboard_actions"]
    if category == "lifecycle" and employment in _csv_set(facts, "onboard_employment") and "onboard_actions" in facts:
        return facts["onboard_actions"]
    if category == "access" and intake == "request" and "access_request_action" in facts:
        return facts["access_request_action"]
    if category == "access" and intake == "incident" and "access_incident_action" in facts:
        return facts["access_incident_action"]
    if intake == "inquiry":
        aged = facts.get("aged_inquiry_hours")
        if (
            aged is not None
            and int(ticket.get("hours_open") or 0) >= int(aged)
            and "aged_inquiry_action" in facts
        ):
            return facts["aged_inquiry_action"]
        if "action_inquiry" in facts:
            return facts["action_inquiry"]
        return "acknowledge"
    specific = f"action_{category}_{intake}"
    if specific in facts:
        return facts[specific]
    if intake == "request" and "action_request" in facts:
        return facts["action_request"]
    return "acknowledge"


def _priority(requester: dict[str, Any], ticket: dict[str, Any], facts: dict[str, str]) -> str | None:
    required = (
        "offboard_priority",
        "onboard_priority",
        "outage_priority",
        "incident_priority",
        "request_priority",
        "inquiry_priority",
        "aged_inquiry_hours",
        "aged_inquiry_priority",
    )
    if any(key not in facts for key in required):
        return None
    employment = str(requester.get("employment") or "")
    category = str(ticket.get("category") or "")
    intake = str(ticket.get("intake_type") or "")
    offboard = _csv_set(facts, "offboard_employment") or {"leaving", "left"}
    onboard = _csv_set(facts, "onboard_employment") or {"new_hire"}
    if category == "lifecycle" and employment in offboard:
        return facts["offboard_priority"]
    if category == "lifecycle" and employment in onboard:
        return facts["onboard_priority"]
    if ticket.get("shared_outage"):
        return facts["outage_priority"]
    if intake == "incident":
        return facts["incident_priority"]
    if intake == "request":
        return facts["request_priority"]
    if intake == "inquiry" and int(ticket.get("hours_open") or 0) >= int(facts["aged_inquiry_hours"]):
        return facts["aged_inquiry_priority"]
    if intake == "inquiry":
        return facts["inquiry_priority"]
    return None


def decide_from_skill_text(
    requester: dict[str, Any],
    ticket: dict[str, Any],
    facts: dict[str, str],
) -> dict[str, str]:
    """Apply only the lines the skills actually revealed. Missing lines mean a wrong filing."""
    signal = str(ticket.get("security_signal") or "none")
    p1 = _csv_set(facts, "p1_signals")
    action_key = f"action_{signal}"
    if signal in p1 and all(key in facts for key in ("p1_type", "p1_category", "p1_priority", "p1_group", action_key)):
        return {
            "ticket_type": facts["p1_type"],
            "category": facts["p1_category"],
            "priority": facts["p1_priority"],
            "assignment_group": facts["p1_group"],
            "actions": facts[action_key],
        }
    if "group_access" not in facts:
        return dict(WRONG)

    category = str(ticket.get("category") or "")
    employment = str(requester.get("employment") or "")
    ticket_type = str(ticket.get("intake_type") or "")
    if category == "lifecycle" and employment in _csv_set(facts, "offboard_employment") and "offboard_actions" in facts:
        ticket_type = "request"
    elif category == "lifecycle" and employment in _csv_set(facts, "onboard_employment") and "onboard_actions" in facts:
        ticket_type = "request"

    group = facts.get(f"group_{category}")
    if not group:
        return dict(WRONG)
    priority = _priority(requester, ticket, facts) or "unset"
    return {
        "ticket_type": ticket_type,
        "category": category,
        "priority": priority,
        "assignment_group": group,
        "actions": _actions_text(requester, ticket, facts),
    }


def choose_action(request: dict[str, Any]) -> dict[str, Any]:
    """Return the next chat message: one tool call, or a final assistant message."""
    messages = list(request.get("messages") or [])
    state = walk(messages)
    prose = state["prose"]
    requester_id = _REQUESTER_RE.search(prose)
    ticket_id = _TICKET_RE.search(prose)
    requester_token = requester_id.group(0) if requester_id else ""
    ticket_token = ticket_id.group(0) if ticket_id else ""
    catalog = set(state["catalog"])

    def tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        call_id = f"call_{len(state['completed']) + 1}"
        choice = {
            "kind": "tool",
            "name": name,
            "arguments": arguments,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }
                ],
            },
        }
        print(f"[mock] {name} {choice['message']['tool_calls'][0]['function']['arguments']}", file=sys.stderr, flush=True)
        return choice

    for name in SKILL_ORDER:
        if name in catalog and not _did(state, "activate_skill", name=name):
            return tool("activate_skill", {"name": name})
    if "priority-matrix" in catalog and "incident_priority" not in state["facts"]:
        return tool(
            "read_skill_file",
            {"name": "priority-matrix", "relative_path": "references/priority-matrix.md"},
        )
    if state["requester"] is None and requester_token:
        return tool("lookup_requester", {"requester_id": requester_token})
    if state["ticket"] is None and ticket_token:
        return tool("lookup_ticket", {"ticket_id": ticket_token})
    if not state["filed"] and state["requester"] and state["ticket"]:
        filing = decide_from_skill_text(state["requester"], state["ticket"], state["facts"])
        return tool(
            "file_triage",
            {
                "ticket_id": state["ticket"]["ticket_id"],
                "ticket_type": filing["ticket_type"],
                "category": filing["category"],
                "priority": filing["priority"],
                "assignment_group": filing["assignment_group"],
                "actions": filing["actions"],
                "requester_message": "I've recorded the triage and the next step on your ticket.",
            },
        )

    filing = dict(WRONG)
    ticket = ticket_token or "the ticket"
    for name, arguments, _output in reversed(state["completed"]):
        if name == "file_triage":
            filing = {
                "ticket_type": str(arguments.get("ticket_type") or filing["ticket_type"]),
                "category": str(arguments.get("category") or filing["category"]),
                "priority": str(arguments.get("priority") or filing["priority"]),
                "assignment_group": str(arguments.get("assignment_group") or filing["assignment_group"]),
                "actions": str(arguments.get("actions") or filing["actions"]),
            }
            ticket = str(arguments.get("ticket_id") or ticket)
            break
    content = (
        f"Filed {filing['ticket_type']} {filing['priority']} on {ticket} "
        f"to {filing['assignment_group']}. Actions: {filing['actions']}."
    )
    print(f"[mock] final: {content}", file=sys.stderr, flush=True)
    return {"kind": "message", "message": {"role": "assistant", "content": content}}


def completion(request: dict[str, Any]) -> dict[str, Any]:
    action = choose_action(request)
    message = action["message"]
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 0,
        "model": request.get("model") or MODEL_NAME,
        "choices": [{"index": 0, "finish_reason": finish, "message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[mock] {self.address_string()} {fmt % args}", file=sys.stderr, flush=True)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"/v1/models", "/models"}:
            body = {
                "object": "list",
                "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "ticketnow-demo"}],
            }
            self._send(200, body)
            return
        self._send(200, {"status": "ok", "model": MODEL_NAME})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "Expected a JSON chat completion request."})
            return
        if self.path.rstrip("/").endswith("/chat/completions"):
            self._send(200, completion(request))
            return
        self._send(404, {"error": f"No route for {self.path}. This mock serves chat completions."})

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def serve(port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mock IT lead on http://127.0.0.1:{port}/v1  model={MODEL_NAME}", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    chosen = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    serve(chosen)
