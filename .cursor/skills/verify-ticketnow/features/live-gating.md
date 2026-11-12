# Live run gating

## Sub-features

- The page has no mode control. Run starts live. It is enabled only when the server already has a real key, a base URL, and a model name.
- It stays disabled until the server process already has a real `POLICY_API_KEY`, `POLICY_BASE_URL`, and `POLICY_MODEL_NAME` (`POLICY_MODEL` is an alias). `POLICY_MODEL_TYPE` must be `vllm_model` or `openai_model`.
- When Run is enabled, `#mode-detail` names the model, the host, and the adapter. The page has no key field.
- Starting it is a real model call. This journey does not press Run.

## How to get to it (user POV)

Open the briefing page. There is no mode control. With no key configured, Run is disabled and the detail says Live mode stays off until `POLICY_API_KEY` is set on the server. When the server was started with a real key and the base URL and model name, Run is enabled and the detail names that model and host. Stop there.

End state with no live configuration: `GET /api/briefing` has `modes.live.enabled` false and a `reason` that names the missing `POLICY_*` variable, and `#run-button` is disabled.

End state with a real key, base URL, and model name already on the server: `modes.live.enabled` is true, `model_name` and `endpoint_host` are non-empty, and `#run-button` is enabled. Do not click it unless a live call is the intended test.

## Driving it with Playwright and curl

```bash
curl -s "$BASE/api/briefing" | python -c 'import json,sys; live=json.load(sys.stdin)["modes"]["live"]; print(live["enabled"]); print(live.get("reason","")); print(live.get("model_name",""))'
```

In Playwright, there is no `input[name="mode"]`. `#run-button` disabled must match `modes.live.enabled === false` when `DEMO_SHOW_MOCK` is unset. When the button is enabled, `#mode-detail` contains the model name from the briefing. Do not click it unless a live call is the intended test.

Do not `POST /api/runs` with `{"mode":"live"}` from this skill. Do not send that request to the Railway host.

## Gotchas

Placeholder keys (`mock`, `changeme`, `your-key`, `your-api-key`, `sk-your-key-here`, `replace-me`, `paste-your-key`) leave Live off, with reason `POLICY_API_KEY is still a placeholder. Live mode stays off.` An empty key says it stays off until `POLICY_API_KEY` is set. A missing base URL or model name has its own reason. The journey fails if the reason does not match the environment you actually started.

`python -m web` loads `.env` without overriding variables the process already has. A key in the shell or in `.env` turns Live on even though `launch.sh` did not export one. Doctor prints `modes.live`. If Live is on and you did not mean to call a model, do not press Run.

The Railway deployment is the wrong place to test this. A Live run may already be in progress there, and this skill must not start another.
