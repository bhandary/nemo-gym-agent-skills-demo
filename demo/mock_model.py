"""Deterministic stand-in for an OpenAI-compatible chat model.

This is not a language model. It follows the skill text that is actually in
the conversation. If the refund rate card was never read, refund cases get a
wrong disposition. If the escalation playbook was never loaded, safety and
high-value cases miss the short-circuit too.

NeMo Gym's ``vllm_model`` server translates the Responses API to
``POST {base_url}/chat/completions``. This server speaks that dialect.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MODEL_NAME = "mock-desk-associate"
DEFAULT_PORT = 43117

_KEY_RE = re.compile(r"(?m)^([a-z][a-z0-9_]*):\s*(\S+)\s*$")
_CATALOG_RE = re.compile(r"(?m)^- ([a-z0-9-]+): ")
_ORDER_RE = re.compile(r"NW-\d+")
_TICKET_RE = re.compile(r"T-\d+")


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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
    order: dict[str, Any] | None = None
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
        if name == "lookup_order" and "merchandise_usd" in payload:
            order = payload
        if name == "lookup_ticket" and "ticket_id" in payload:
            ticket = payload
        if name == "file_resolution" and "error" not in payload:
            filed = True
    return {
        "catalog": catalog,
        "completed": completed,
        "facts": facts,
        "order": order,
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


def decide_from_skill_text(order: dict[str, Any], ticket: dict[str, Any], facts: dict[str, str]) -> tuple[str, float, bool]:
    """Apply only the lines the skills actually revealed. Missing lines mean a wrong filing."""
    if ticket.get("safety_flag") and "safety_flag_disposition" in facts:
        return facts["safety_flag_disposition"], 0.0, True
    high = facts.get("high_value_merchandise_usd")
    if (
        high is not None
        and float(order["merchandise_usd"]) > float(high)
        and "high_value_disposition" in facts
    ):
        return facts["high_value_disposition"], 0.0, True
    if "full_refund_disposition" not in facts:
        return "refund", float(order["merchandise_usd"]), False
    days = int(order["days_since_delivery"])
    if not order["opened"] and days <= int(facts["unopened_full_refund_days"]):
        return facts["full_refund_disposition"], float(order["merchandise_usd"]), False
    if (
        order["opened"]
        and order["damage_in_transit"]
        and days <= int(facts["opened_damage_days"])
    ):
        refund = money(
            Decimal(str(order["merchandise_usd"]))
            * Decimal(facts["opened_damage_refund_percent"])
            / Decimal(100)
        )
        return facts["partial_refund_disposition"], refund, False
    if order["customer_tier"] == "gold":
        return facts["gold_no_refund_disposition"], 0.0, False
    return facts["standard_no_refund_disposition"], 0.0, False


def choose_action(request: dict[str, Any]) -> dict[str, Any]:
    """Return the next chat message: one tool call, or a final assistant message."""
    messages = list(request.get("messages") or [])
    state = walk(messages)
    prose = state["prose"]
    order_id = _ORDER_RE.search(prose)
    ticket_id = _TICKET_RE.search(prose)
    order_token = order_id.group(0) if order_id else ""
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

    if "escalation-playbook" in catalog and not _did(state, "activate_skill", name="escalation-playbook"):
        return tool("activate_skill", {"name": "escalation-playbook"})
    if "refund-policy" in catalog and not _did(state, "activate_skill", name="refund-policy"):
        return tool("activate_skill", {"name": "refund-policy"})
    if "refund-policy" in catalog and "unopened_full_refund_days" not in state["facts"]:
        return tool(
            "read_skill_file",
            {"name": "refund-policy", "relative_path": "references/rate-card.md"},
        )
    if "close-the-ticket" in catalog and not _did(state, "activate_skill", name="close-the-ticket"):
        return tool("activate_skill", {"name": "close-the-ticket"})
    if state["order"] is None and order_token:
        return tool("lookup_order", {"order_id": order_token})
    if state["ticket"] is None and ticket_token:
        return tool("lookup_ticket", {"ticket_id": ticket_token})
    if not state["filed"] and state["order"] and state["ticket"]:
        disposition, refund, escalate = decide_from_skill_text(state["order"], state["ticket"], state["facts"])
        return tool(
            "file_resolution",
            {
                "ticket_id": state["ticket"]["ticket_id"],
                "disposition": disposition,
                "refund_usd": refund,
                "escalate": escalate,
                "customer_message": "I've recorded the outcome on your ticket and noted the amount.",
            },
        )

    disposition = "unresolved"
    refund = 0.0
    escalate = False
    ticket = ticket_token or "the ticket"
    for name, arguments, _output in reversed(state["completed"]):
        if name == "file_resolution":
            disposition = str(arguments.get("disposition") or disposition)
            try:
                refund = float(arguments.get("refund_usd"))
            except (TypeError, ValueError):
                refund = 0.0
            escalate = bool(arguments.get("escalate"))
            ticket = str(arguments.get("ticket_id") or ticket)
            break
    escalated = "yes" if escalate else "no"
    content = f"Filed {disposition} on {ticket}. Refund ${refund:.2f}. Escalated: {escalated}."
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
                "data": [{"id": MODEL_NAME, "object": "model", "owned_by": "northwind-demo"}],
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
    print(f"Mock desk model on http://127.0.0.1:{port}/v1  model={MODEL_NAME}", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    chosen = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    serve(chosen)
