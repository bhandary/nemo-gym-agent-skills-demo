"""Progressive disclosure for Agent Skills, used by the desk agent.

NeMo Gym does not parse or activate skills. It stamps ``skills_ref`` on the
``/run`` body. This module is the agent's native runtime: stage the directory
with ``nemo_gym.skills.stage_skills``, show name and description only, and
load a ``SKILL.md`` body or a referenced file when the model asks.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

try:
    from nemo_gym.agents.skills import SKILL_MD_FILENAME, parse_skill_md, stage_skills
except ImportError:  # NeMo Gym 0.7.0 keeps the helpers here. Later docs moved them.
    from nemo_gym.skills import SKILL_MD_FILENAME, parse_skill_md, stage_skills


CATALOG_HEADING = "Available skills"
NO_SKILLS_BANNER = "No operational skills are loaded for this run."


def stage_request_skills(skills_path: str) -> tuple[Path, Path]:
    """Copy ``skills_path`` into a fresh directory. Caller deletes the parent."""
    root = Path(tempfile.mkdtemp(prefix="ticketnow-skills-"))
    dest = root / "skills"
    try:
        stage_skills(skills_path, dest)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root, dest


def skill_metadata(staged_dir: Path) -> list[Any]:
    found = []
    for skill_dir in sorted(path for path in staged_dir.iterdir() if path.is_dir()):
        skill_md = skill_dir / SKILL_MD_FILENAME
        if skill_md.is_file():
            found.append(parse_skill_md(skill_md))
    return found


def render_catalog(staged_dir: Path) -> str:
    lines = [
        CATALOG_HEADING,
        "Load a skill with activate_skill before you follow it. A description is not the instructions.",
        "",
    ]
    for meta in skill_metadata(staged_dir):
        description = (meta.description or "").strip() or "(no description)"
        lines.append(f"- {meta.name}: {description}")
    return "\n".join(lines)


def render_no_skills() -> str:
    return (
        f"{NO_SKILLS_BANNER} TicketNow's policy documents are not in your context. "
        "Use the tools and the ticket text. Do not invent a priority, an assignment group, or an action code."
    )


def _skill_tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
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


def skill_tools() -> list[dict[str, Any]]:
    return [
        _skill_tool(
            "activate_skill",
            "Load the full instructions for one skill from the catalog. Call this before following that skill.",
            {"name": {"type": "string", "description": "Skill name from the catalog."}},
            ["name"],
        ),
        _skill_tool(
            "read_skill_file",
            "Read a file inside a skill directory. Use a relative path the skill instructions mention.",
            {
                "name": {"type": "string", "description": "Skill name."},
                "relative_path": {"type": "string", "description": "Path relative to the skill directory."},
            },
            ["name", "relative_path"],
        ),
    ]


def _skill_dir(staged_dir: Path, name: str) -> Path | None:
    for skill_dir in staged_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / SKILL_MD_FILENAME
        if not skill_md.is_file():
            continue
        if parse_skill_md(skill_md).name == name:
            return skill_dir
    return None


def _body(skill_md: Path) -> str:
    lines = skill_md.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        return "\n".join(lines).strip()
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1 :]).strip()
    return ""


def _relative_files(skill_dir: Path) -> list[str]:
    files = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and path.name != SKILL_MD_FILENAME:
            files.append(path.relative_to(skill_dir).as_posix())
    return files


def activate_skill(staged_dir: Path, name: str) -> str:
    skill_dir = _skill_dir(staged_dir, name)
    if skill_dir is None:
        known = [meta.name for meta in skill_metadata(staged_dir)]
        return json.dumps({"error": f"No skill named {name}.", "available": known})
    return json.dumps(
        {
            "name": name,
            "instructions": _body(skill_dir / SKILL_MD_FILENAME),
            "files": _relative_files(skill_dir),
        }
    )


def read_skill_file(staged_dir: Path, name: str, relative_path: str) -> str:
    skill_dir = _skill_dir(staged_dir, name)
    if skill_dir is None:
        known = [meta.name for meta in skill_metadata(staged_dir)]
        return json.dumps({"error": f"No skill named {name}.", "available": known})
    requested = Path(relative_path)
    if requested.is_absolute() or any(part == ".." for part in requested.parts):
        return json.dumps({"error": "Path must stay inside the skill directory."})
    target = (skill_dir / requested).resolve()
    try:
        target.relative_to(skill_dir.resolve())
    except ValueError:
        return json.dumps({"error": "Path must stay inside the skill directory."})
    if not target.is_file():
        return json.dumps({"error": f"No file {relative_path} in skill {name}.", "files": _relative_files(skill_dir)})
    return json.dumps({"name": name, "path": relative_path, "content": target.read_text(encoding="utf-8")})


def handle_skill_tool(staged_dir: Path, name: str, arguments: dict[str, Any]) -> str | None:
    """Return a JSON string when ``name`` is a skill tool, else None."""
    if name == "activate_skill":
        return activate_skill(staged_dir, str(arguments.get("name") or ""))
    if name == "read_skill_file":
        return read_skill_file(
            staged_dir,
            str(arguments.get("name") or ""),
            str(arguments.get("relative_path") or ""),
        )
    return None


def prepare_model_body(params: Any, staged_dir: Path | None) -> dict[str, Any]:
    """Copy the task's Responses request and attach this run's skill catalog."""
    body = params.model_dump(mode="json", exclude_none=True)
    incoming = body.get("input")
    messages = list(incoming) if isinstance(incoming, list) else [{"role": "user", "content": str(incoming)}]
    # Put the catalog first so a chat-completions model server folds it into the
    # leading system message. A developer message after the user stays a
    # "developer" turn, which many OpenAI-compatible endpoints reject.
    if staged_dir is None:
        messages.insert(0, {"role": "developer", "content": render_no_skills(), "type": "message"})
        return body | {"input": messages, "parallel_tool_calls": False}

    messages.insert(0, {"role": "developer", "content": render_catalog(staged_dir), "type": "message"})
    tools = list(body.get("tools") or [])
    tools.extend(skill_tools())
    return body | {"input": messages, "tools": tools, "parallel_tool_calls": False}
