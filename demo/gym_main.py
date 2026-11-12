"""Gym CLI entry that applies the container Ray settings first."""

from __future__ import annotations

import sys

from demo.ray_bootstrap import install


install()

from nemo_gym.cli.main import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main() or 0)
