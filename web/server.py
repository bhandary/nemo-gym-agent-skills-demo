"""Briefing server for the Northwind Agent Skills demo.

One process serves the page, the recorded sample, and, when asked, a real
NeMo Gym run. Keys stay in the server environment.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from demo.present import load_sample_view
from demo.runner import DemoRunError
from demo.settings import load_dotenv, nemo_gym_version
from web.briefing import briefing
from web.runs import RunBusy, RunManager, RunUnknown


ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
INDEX = STATIC / "index.html"


class RunRequest(BaseModel):
    mode: str = Field(pattern="^(recorded|mock|live)$")


def create_app(root: Path | None = None) -> FastAPI:
    repo = root or ROOT
    load_dotenv(repo / ".env")
    manager = RunManager(repo)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.runs.shutdown()

    app = FastAPI(title="Northwind support desk", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.runs = manager
    app.state.root = repo

    @app.get("/health")
    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "northwind-desk", "nemo_gym": nemo_gym_version()}

    @app.get("/api/briefing")
    def api_briefing() -> dict:
        return briefing(app.state.root)

    @app.get("/api/sample")
    def api_sample() -> dict:
        try:
            return load_sample_view(app.state.root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/runs")
    def api_start(body: RunRequest) -> dict:
        try:
            return app.state.runs.start(body.mode)
        except RunBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DemoRunError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/current")
    def api_current() -> dict:
        return {"run": app.state.runs.latest()}

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: str) -> dict:
        try:
            return app.state.runs.snapshot(run_id)
        except RunUnknown as exc:
            raise HTTPException(status_code=404, detail="No run with that id.") from exc

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
