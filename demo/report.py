"""Side-by-side scores and one readable episode trace.

The table is computed by rescoring each rollout with the same policy the
resources server uses. Gym's own ``reward`` field is shown next to it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from resources_servers.northwind_desk.policy import CASES, score_output


VARIANTS = (
    ("no_skills", "No skills"),
    ("full_skills", "Full skills"),
    ("without_refund_policy", "Missing refund skill"),
)


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"Missing rollout file: {path}")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"No rollouts in {path}")
    return rows


def _user_text(row: dict[str, Any]) -> str:
    params = row.get("responses_create_params") or {}
    chunks = []
    for item in params.get("input") or []:
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, str):
                chunks.append(content)
    return "\n".join(chunks)


def _case_for(row: dict[str, Any]) -> dict[str, Any]:
    metadata = ((row.get("response") or {}).get("metadata")) or {}
    case_id = metadata.get("case_id") or row.get("case_id")
    if case_id:
        for case in CASES:
            if case["case_id"] == case_id:
                return case
    text = _user_text(row)
    for case in CASES:
        if case["user"] in text or case["ticket"]["ticket_id"] in text:
            return case
    raise SystemExit("A rollout could not be matched to a Northwind ticket.")


def _grade(row: dict[str, Any]) -> Any:
    return score_output((row.get("response") or {}).get("output") or [], _case_for(row))


def _index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found = {}
    for row in rows:
        found[_case_for(row)["case_id"]] = row
    return found


def _money(value: float) -> str:
    return f"${value:.2f}"


def comparison_markdown(by_variant: dict[str, dict[str, dict[str, Any]]]) -> str:
    lines = [
        "| Ticket | No skills | Full skills | Missing refund skill |",
        "| --- | --- | --- | --- |",
    ]
    means = {key: [] for key, _label in VARIANTS}
    passes = {key: 0 for key, _label in VARIANTS}
    for case in CASES:
        cells = [f"{case['ticket']['ticket_id']} {case['case_id']}"]
        for key, _label in VARIANTS:
            row = by_variant[key].get(case["case_id"])
            if row is None:
                cells.append("missing")
                continue
            graded = _grade(row)
            gym_reward = row.get("reward")
            mark = "pass" if graded.decision == 1.0 else "fail"
            gym = f"{float(gym_reward):.1f}" if isinstance(gym_reward, (int, float)) else "n/a"
            cells.append(f"{graded.reward:.1f} reward, {mark} (Gym {gym})")
            means[key].append(graded.reward)
            passes[key] += int(graded.decision == 1.0)
        lines.append("| " + " | ".join(cells) + " |")
    summary = ["Mean reward"]
    success = ["Correct decisions"]
    for key, _label in VARIANTS:
        values = means[key]
        summary.append(f"{sum(values) / len(values):.2f}" if values else "n/a")
        success.append(f"{passes[key]} / {len(CASES)}")
    lines.append("| " + " | ".join(summary) + " |")
    lines.append("| " + " | ".join(success) + " |")
    return "\n".join(lines) + "\n"


def _short(value: Any, limit: int = 240) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def trace_markdown(row: dict[str, Any]) -> str:
    case = _case_for(row)
    graded = _grade(row)
    skills = row.get("skills_ref") or {}
    names = [item.get("name") for item in skills.get("skills") or [] if isinstance(item, dict)]
    lines = [
        f"# Episode trace: {case['case_id']}",
        "",
        f"Customer ticket {case['ticket']['ticket_id']}, order {case['order']['order_id']}.",
        "",
        f"Skills directory: `{skills.get('path', 'none')}`",
        f"Skills hash: `{skills.get('hash', 'none')}`",
        f"Skills loaded: {', '.join(names) if names else 'none'}",
        "",
        "The agent sees the skill catalog first. It loads a skill, then reads the rate card, then looks up the ticket, then files one resolution.",
        "",
    ]
    step = 0
    for item in (row.get("response") or {}).get("output") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "function_call":
            step += 1
            arguments = item.get("arguments")
            try:
                shown = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                shown = arguments
            lines.append(f"{step}. **{item.get('name')}** `{_short(shown, 300)}`")
        elif kind == "function_call_output":
            lines.append(f"   - returned `{_short(item.get('output'), 280)}`")
        elif kind == "message" and item.get("role") == "assistant":
            content = item.get("content")
            if isinstance(content, list):
                content = " ".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
            lines.append("")
            lines.append(f"Associate: {content}")
    lines.extend(
        [
            "",
            f"Verifier: procedure {graded.procedure:.0f}, decision {graded.decision:.0f}, reward {graded.reward:.1f}.",
            f"Expected {graded.expected.disposition}, refund {_money(graded.expected.refund_usd)}, escalate {graded.expected.escalate}.",
            f"Notes: {graded.notes}.",
            f"Gym recorded reward: {row.get('reward')}.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(results: Path, comparison_path: Path, trace_path: Path, trace_case: str) -> str:
    by_variant = {key: _index(_load(results / f"{key}.jsonl")) for key, _label in VARIANTS}
    comparison = comparison_markdown(by_variant)
    full = by_variant["full_skills"].get(trace_case)
    if full is None:
        raise SystemExit(f"Full-skills rollouts have no case {trace_case}.")
    trace = trace_markdown(full)
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(comparison, encoding="utf-8")
    trace_path.write_text(trace, encoding="utf-8")
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Northwind skill variants.")
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--comparison", type=Path, default=None)
    parser.add_argument("--trace", type=Path, default=None)
    parser.add_argument("--trace-case", default="dented-kettle")
    args = parser.parse_args()
    comparison_path = args.comparison or (args.results / "comparison.md")
    trace_path = args.trace or (args.results / "trace.md")
    table = write_report(args.results, comparison_path, trace_path, args.trace_case)
    print(table)
    print(f"Wrote {comparison_path}")
    print(f"Wrote {trace_path}")


if __name__ == "__main__":
    main()
