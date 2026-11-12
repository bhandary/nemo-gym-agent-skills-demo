"""Northwind support-desk resources server.

Tools return order and ticket facts. ``verify`` scores the agent's
``file_resolution`` call with the fixed company policy. Skills are not
read here. NeMo Gym applies them as a run-level knob on the agent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, PrivateAttr

_SERVER_DIR = Path(__file__).resolve().parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

import policy  # noqa: E402

from nemo_gym.base_resources_server import (
    BaseMultiRewardVerifyResponse,
    BaseResourcesServerConfig,
    BaseSeedSessionRequest,
    BaseSeedSessionResponse,
    BaseVerifyRequest,
    ResourcesCloseSessionRequest,
    ResourcesCloseSessionResponse,
    ResourcesSeedSessionRequest,
    ResourcesSeedSessionResponse,
    SimpleResourcesServer,
)
from nemo_gym.episode_types import EpisodeId, TaskId


class NorthwindDeskConfig(BaseResourcesServerConfig):
    pass


class LookupOrderRequest(BaseModel):
    order_id: str


class LookupTicketRequest(BaseModel):
    ticket_id: str


class FileResolutionRequest(BaseModel):
    ticket_id: str
    disposition: str
    refund_usd: float
    escalate: bool
    customer_message: str


class NorthwindVerifyRequest(BaseVerifyRequest):
    model_config = ConfigDict(extra="allow")
    case_id: str


class NorthwindVerifyResponse(BaseMultiRewardVerifyResponse):
    model_config = ConfigDict(extra="allow")
    case_id: str
    procedure: float
    decision: float
    score_notes: str


class NorthwindDeskResourcesServer(SimpleResourcesServer):
    ray_enabled: ClassVar[bool] = False
    config: NorthwindDeskConfig
    _session_episodes: dict[str, tuple[EpisodeId, TaskId]] = PrivateAttr(default_factory=dict)
    _closed_session_ids: set[str] = PrivateAttr(default_factory=set)

    def setup_webserver(self) -> FastAPI:
        app = super().setup_webserver()
        app.post("/lookup_order")(self.lookup_order)
        app.post("/lookup_ticket")(self.lookup_ticket)
        app.post("/file_resolution")(self.file_resolution)
        return app

    async def seed_session(
        self,
        body: ResourcesSeedSessionRequest | BaseSeedSessionRequest,
    ) -> ResourcesSeedSessionResponse | BaseSeedSessionResponse:
        if not isinstance(body, ResourcesSeedSessionRequest):
            return BaseSeedSessionResponse()
        resources_session_id = body.resources_session_id
        if resources_session_id in self._closed_session_ids:
            raise ValueError(f"Resources session is already closed: {resources_session_id}")
        identity = self._session_episodes.setdefault(resources_session_id, (body.episode_id, body.task_id))
        if identity != (body.episode_id, body.task_id):
            raise ValueError("resources_session_id is already bound to another episode or task")
        return ResourcesSeedSessionResponse(resources_session_id=resources_session_id)

    async def close_resources_session(self, body: ResourcesCloseSessionRequest) -> ResourcesCloseSessionResponse:
        resources_session_id = body.resources_session_id
        identity = self._session_episodes.get(resources_session_id)
        if identity is not None and body.episode_id != identity[0]:
            raise ValueError("episode_id does not match the seeded resources session")
        self._session_episodes.pop(resources_session_id, None)
        self._closed_session_ids.add(resources_session_id)
        return ResourcesCloseSessionResponse(resources_session_id=resources_session_id)

    async def lookup_order(self, body: LookupOrderRequest) -> dict[str, Any]:
        return policy.lookup_order_payload(body.order_id)

    async def lookup_ticket(self, body: LookupTicketRequest) -> dict[str, Any]:
        return policy.lookup_ticket_payload(body.ticket_id)

    async def file_resolution(self, body: FileResolutionRequest) -> dict[str, Any]:
        return {
            "accepted": True,
            "ticket_id": body.ticket_id,
            "disposition": body.disposition,
            "refund_usd": body.refund_usd,
            "escalate": body.escalate,
        }

    async def verify(self, body: NorthwindVerifyRequest) -> NorthwindVerifyResponse:
        try:
            case = policy.case_by_id(body.case_id)
        except KeyError:
            return NorthwindVerifyResponse(
                responses_create_params=body.responses_create_params,
                response=body.response,
                case_id=body.case_id,
                reward=0.0,
                reward_components={"procedure": 0.0, "decision": 0.0},
                procedure=0.0,
                decision=0.0,
                score_notes=f"unknown case_id {body.case_id}",
            )
        graded = policy.score_output(list(body.response.output), case)
        # Rollout collection keeps `response` on the result. The agent's /run route
        # is typed as the base verify response, so top-level extras can be dropped
        # on the way out. The grade also lives here, as strings, where it survives.
        stamped = body.response.model_copy(
            update={
                "metadata": {
                    "case_id": body.case_id,
                    "procedure": f"{graded.procedure:.4f}",
                    "decision": f"{graded.decision:.4f}",
                    "score_notes": graded.notes[:500],
                    "expected_disposition": graded.expected.disposition,
                    "expected_refund_usd": f"{graded.expected.refund_usd:.2f}",
                    "expected_escalate": "true" if graded.expected.escalate else "false",
                }
            }
        )
        return NorthwindVerifyResponse(
            responses_create_params=body.responses_create_params,
            response=stamped,
            case_id=body.case_id,
            reward=graded.reward,
            reward_components={"procedure": graded.procedure, "decision": graded.decision},
            procedure=graded.procedure,
            decision=graded.decision,
            score_notes=graded.notes,
        )


if __name__ == "__main__":
    NorthwindDeskResourcesServer.run_webserver()
