"""Build the missing-skill directory from the committed full set.

The shared skills must be the same bytes in both variants. The demo
regenerates ``skills/without_priority_matrix`` at the start of every run so a
presenter edit to the full set cannot silently drift.
"""

from __future__ import annotations

import shutil
from pathlib import Path


SHARED_SKILLS = (
    "security-first-response",
    "ticket-classification",
    "access-request-policy",
)


def sync_without_priority_matrix(root: Path) -> Path:
    source = root / "skills" / "full"
    dest = root / "skills" / "without_priority_matrix"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in SHARED_SKILLS:
        shutil.copytree(source / name, dest / name)
    return dest
