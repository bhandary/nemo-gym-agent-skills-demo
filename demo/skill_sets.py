"""Skill folders the demo can score.

The full set is committed. Every other folder is copied from it at the start
of a run, so a playbook edited in ``skills/full`` cannot drift from the
variant that leaves it out.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


SKILLS = (
    ("security-first-response", "Security first response"),
    ("ticket-classification", "Classify and route"),
    ("access-request-policy", "Access request policy"),
    ("priority-matrix", "Priority matrix"),
)

SHARED_SKILLS = tuple(name for name, _title in SKILLS if name != "priority-matrix")

_OMIT_LABEL = {
    "security-first-response": "Without security first response",
    "ticket-classification": "Without classification",
    "access-request-policy": "Without the access policy",
    "priority-matrix": "Without the priority matrix",
}

_KNOWN = {name for name, _title in SKILLS}


class UnknownSkill(ValueError):
    pass


def _ordered(skill_names: list[str] | tuple[str, ...]) -> list[str]:
    chosen = set(skill_names)
    unknown = sorted(chosen - _KNOWN)
    if unknown:
        raise UnknownSkill("Unknown skill: " + ", ".join(unknown))
    return [name for name, _title in SKILLS if name in chosen]


def selection_config(skill_names: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Describe the folder a lead with exactly these playbooks would open."""
    ordered = _ordered(skill_names)
    if len(ordered) == len(SKILLS):
        return {
            "id": "full_skills",
            "label": "All four skills",
            "skills": ordered,
            "path": "skills/full",
        }
    if not ordered:
        return {"id": "no_skills", "label": "No skills", "skills": [], "path": ""}
    missing = [name for name, _title in SKILLS if name not in ordered]
    if len(missing) == 1:
        omitted = missing[0]
        config_id = "without_" + omitted.replace("-", "_")
        return {
            "id": config_id,
            "label": _OMIT_LABEL[omitted],
            "skills": ordered,
            "path": f"skills/{config_id}",
        }
    return {
        "id": "selected",
        "label": "Selected playbooks",
        "skills": ordered,
        "path": "skills/selected",
    }


def run_plan(
    skill_names: list[str] | tuple[str, ...] | None = None,
    *,
    compare_without_matrix: bool = True,
) -> list[dict[str, Any]]:
    """Baseline with no skills, the selected playbooks, and the matrix ablation when it still applies."""
    if skill_names is None:
        skill_names = [name for name, _title in SKILLS]
    primary = selection_config(skill_names)
    plan = [{"id": "no_skills", "label": "No skills", "skills": [], "path": ""}]
    if primary["id"] != "no_skills":
        plan.append(primary)
    if (
        compare_without_matrix
        and "priority-matrix" in primary["skills"]
        and primary["id"] != "without_priority_matrix"
    ):
        plan.append(selection_config([name for name in primary["skills"] if name != "priority-matrix"]))
    return plan


def materialize(root: Path, config: dict[str, Any]) -> Path | None:
    """Copy the selected playbooks into the folder Gym will hash. The full set is left as committed."""
    path = config.get("path") or ""
    if not path or path == "skills/full":
        return root / "skills" / "full" if path else None
    source = root / "skills" / "full"
    dest = root / path
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in config["skills"]:
        shutil.copytree(source / name, dest / name)
    return dest


def sync_without_priority_matrix(root: Path) -> Path:
    dest = materialize(root, selection_config(list(SHARED_SKILLS)))
    if dest is None:
        raise RuntimeError("The priority-matrix ablation did not produce a folder.")
    return dest
