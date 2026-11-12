"""Build the missing-skill directory from the committed full set.

The two shared skills must be the same bytes in both variants. The demo
regenerates ``skills/without_refund_policy`` at the start of every run so a
presenter edit to the full set cannot silently drift.
"""

from __future__ import annotations

import shutil
from pathlib import Path


SHARED_SKILLS = ("escalation-playbook", "close-the-ticket")


def sync_without_refund(root: Path) -> Path:
    source = root / "skills" / "full"
    dest = root / "skills" / "without_refund_policy"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in SHARED_SKILLS:
        shutil.copytree(source / name, dest / name)
    return dest
