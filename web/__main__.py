"""Start the briefing page. Railway sets PORT; local runs default to 43123."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from web.server import ROOT


def main() -> None:
    bindir = ROOT / ".venv" / "bin"
    if bindir.is_dir():
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
    port = int(os.environ.get("PORT", "43123"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Northwind briefing on http://127.0.0.1:{port}", file=sys.stderr, flush=True)
    uvicorn.run("web.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
