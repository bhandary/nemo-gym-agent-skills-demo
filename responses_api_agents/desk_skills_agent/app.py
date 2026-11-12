"""OpenAI-compatible agent that implements NeMo Gym's skills adapter.

The adapter, from the Agent Skills docs, is three steps:

1. Read ``skills_ref["path"]`` from the ``/run`` body. Rollout collection stamps it.
2. ``stage_skills`` into a per-request directory so concurrent runs do not share files.
3. Let this runtime discover the skills. Discovery follows the Agent Skills
   spec: name and description first, full ``SKILL.md`` only when the model
   activates the skill, referenced files only when the instructions ask.

The policy model is whatever Gym's model server is pointed at
(``policy_base_url``). This agent does not call a vendor SDK itself.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, ClassVar

from fastapi import HTTPException, Request
from pydantic import ConfigDict, Field

_SERVER_DIR = Path(__file__).resolve().parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from skills_runtime import handle_skill_tool, prepare_model_body, stage_request_skills  # noqa: E402

from nemo_gym.base_resources_server import BaseRunRequest, BaseVerifyResponse  # noqa: E402
from nemo_gym.base_responses_api_agent import (  # noqa: E402
    BaseResponsesAPIAgentConfig,
    Body,
    SimpleResponsesAPIAgent,
)
from nemo_gym.config_types import ModelServerRef, ResourcesServerRef  # noqa: E402
from nemo_gym.global_config import SKILLS_REF_KEY_NAME  # noqa: E402
from nemo_gym.openai_utils import (  # noqa: E402
    NeMoGymFunctionCallOutput,
    NeMoGymResponse,
    NeMoGymResponseCreateParamsNonStreaming,
)
from nemo_gym.server_utils import get_response_json, raise_for_status  # noqa: E402


LOG = logging.getLogger(__name__)


class DeskSkillsAgentConfig(BaseResponsesAPIAgentConfig):
    resources_server: ResourcesServerRef
    model_server: ModelServerRef
    max_steps: int = Field(default=10, ge=1)


class DeskRunRequest(BaseRunRequest):
    model_config = ConfigDict(extra="allow")
    case_id: str


class DeskRunResponse(BaseVerifyResponse):
    """Keep the verifier's extra fields on the way back to rollout collection."""

    model_config = ConfigDict(extra="allow")


class DeskSkillsAgent(SimpleResponsesAPIAgent):
    ray_enabled: ClassVar[bool] = False
    config: DeskSkillsAgentConfig

    async def responses(self, body: NeMoGymResponseCreateParamsNonStreaming = Body()) -> NeMoGymResponse:
        raise HTTPException(status_code=400, detail="This agent runs episodes on POST /run.")

    async def run(self, request: Request, body: DeskRunRequest) -> DeskRunResponse:
        skills_ref = (body.model_extra or {}).get(SKILLS_REF_KEY_NAME) or {}
        skills_path = skills_ref.get("path") if isinstance(skills_ref, dict) else None
        staged_root: Path | None = None
        staged_dir: Path | None = None
        try:
            if skills_path:
                staged_root, staged_dir = stage_request_skills(str(skills_path))
                LOG.info("Staged skills from %s into %s", skills_path, staged_dir)
            else:
                LOG.info("No skills_ref on this run. The agent has no operational skills.")

            seed_response = await self.server_client.post(
                server_name=self.config.resources_server.name,
                url_path="/seed_session",
                json=body.model_dump(mode="json"),
                cookies=request.cookies,
            )
            await raise_for_status(seed_response)
            cookies = seed_response.cookies

            model_body = prepare_model_body(body.responses_create_params, staged_dir)
            conversation = list(model_body["input"])
            collected: list[Any] = []
            model_response: NeMoGymResponse | None = None

            for _step in range(self.config.max_steps):
                model_http = await self.server_client.post(
                    server_name=self.config.model_server.name,
                    url_path="/v1/responses",
                    json=model_body | {"input": conversation},
                    cookies=cookies,
                )
                await raise_for_status(model_http)
                model_response = NeMoGymResponse.model_validate(await get_response_json(model_http))
                step_items = [item for item in model_response.output if _item_type(item) != "reasoning"]
                collected.extend(step_items)
                calls = [item for item in step_items if _item_type(item) == "function_call"]
                if not calls:
                    break

                tool_items: list[NeMoGymFunctionCallOutput] = []
                for call in calls:
                    tool_output, cookies = await self._call_tool(call, staged_dir, cookies)
                    tool_items.append(
                        NeMoGymFunctionCallOutput(
                            type="function_call_output",
                            call_id=call.call_id,
                            output=tool_output,
                        )
                    )
                collected.extend(tool_items)
                conversation = conversation + [_dump(item) for item in step_items] + [_dump(item) for item in tool_items]

            if model_response is None:
                raise RuntimeError("The model server returned no response.")

            final = model_response.model_copy(update={"output": collected})
            verify_http = await self.server_client.post(
                server_name=self.config.resources_server.name,
                url_path="/verify",
                json=body.model_dump(mode="json") | {"response": final.model_dump(mode="json")},
                cookies=cookies,
            )
            await raise_for_status(verify_http)
            return DeskRunResponse.model_validate(await get_response_json(verify_http))
        finally:
            if staged_root is not None:
                shutil.rmtree(staged_root, ignore_errors=True)

    async def _call_tool(self, call: Any, staged_dir: Path | None, cookies: Any) -> tuple[str, Any]:
        try:
            arguments = json.loads(call.arguments) if isinstance(call.arguments, str) else {}
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid tool arguments: {exc}"}), cookies
        if not isinstance(arguments, dict):
            arguments = {}
        if staged_dir is not None:
            skill_output = handle_skill_tool(staged_dir, call.name, arguments)
            if skill_output is not None:
                return skill_output, cookies
        tool_http = await self.server_client.post(
            server_name=self.config.resources_server.name,
            url_path=f"/{call.name}",
            json=arguments,
            cookies=cookies,
        )
        return (await tool_http.content.read()).decode(), tool_http.cookies


def _item_type(item: Any) -> str | None:
    if isinstance(item, dict):
        return item.get("type")
    return getattr(item, "type", None)


def _dump(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json", exclude_none=True)
    return item


if __name__ == "__main__":
    DeskSkillsAgent.run_webserver()
