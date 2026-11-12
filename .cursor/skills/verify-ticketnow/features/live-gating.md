# Live run gating

## Sub-features

- Live model is a radio in the same group as Recorded sample. Mock model is not in that group unless the server was started with `DEMO_SHOW_MOCK=1`.
- It stays disabled until the server process already has a real `POLICY_API_KEY`, `POLICY_BASE_URL`, and `POLICY_MODEL_NAME` (`POLICY_MODEL` is an alias). `POLICY_MODEL_TYPE` must be `vllm_model` or `openai_model`.
- When it is on, `#mode-detail` names the model, the host, and the adapter. The page has no key field.
- Starting it is a real model call. This journey does not press Run demo.

## How to get to it (user POV)

Open the briefing page and look at Live model. With no key configured, the control is greyed out and the detail says Live mode stays off until `POLICY_API_KEY` is set on the server. When the server was started with a real key and the base URL and model name, the control can be selected and the detail names that model and host. Stop there.

End state with no live configuration: `GET /api/briefing` has `modes.live.enabled` false and a `reason` that names the missing `POLICY_*` variable, and `input[name="mode"][value="live"]` is disabled.

End state with a real key, base URL, and model name already on the server: `modes.live.enabled` is true, `model_name` and `endpoint_host` are non-empty, and the radio is enabled. Do not click `#run-button` in this state unless a live call is the intended test.

## Driving it with Playwright and curl

```bash
curl -s "$BASE/api/briefing" | python -c 'import json,sys; live=json.load(sys.stdin)["modes"]["live"]; print(live["enabled"]); print(live.get("reason","")); print(live.get("model_name",""))'
```

In Playwright, read `input[name="mode"][value="live"]`. Disabled must match `modes.live.enabled === false`. When the radio is enabled, read `#mode-detail` after checking it and require the model name from the briefing. Then check Recorded sample again so the page is not left on Live.

Do not `POST /api/runs` with `{"mode":"live"}` from this skill. Do not send that request to the Railway host.

## Gotchas

Placeholder keys (`mock`, `changeme`, `your-key`, `your-api-key`, `sk-your-key-here`, `replace-me`, `paste-your-key`) leave Live off, with reason `POLICY_API_KEY is still a placeholder. Live mode stays off.` An empty key says it stays off until `POLICY_API_KEY` is set. A missing base URL or model name has its own reason. The journey fails if the reason does not match the environment you actually started.

`python -m web` loads `.env` without overriding variables the process already has. A key in the shell or in `.env` turns Live on even though `launch.sh` did not export one. Doctor prints `modes.live`. If Live is on and you did not mean to call a model, do not press Run demo.

The Railway deployment is the wrong place to test this. A Live run may already be in progress there, and this skill must not start another.
