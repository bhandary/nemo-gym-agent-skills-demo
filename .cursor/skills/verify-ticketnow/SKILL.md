---
name: verify-ticketnow
description: >-
  Verify the TicketNow IT service desk briefing page (the web UI served by
  python -m web). Use when a change to the page, the run API, skill selection,
  Walk the ticket, or a local mock scoring run needs an end-to-end check before
  it is called done. Do not use it to start Live model, and do not POST a run
  to the Railway deployment. The page shows Recorded sample and Live model.
  Mock model is hidden unless the server was started with DEMO_SHOW_MOCK=1.
---

# Verify TicketNow

This skill checks the TicketNow IT service desk demo in this repository. The primary surface is the briefing page at `python -m web` (`./run_ui.sh` and `make ui` start that same process). The page talks to `GET /health`, `GET /api/briefing`, `GET /api/sample`, `POST /api/runs`, `GET /api/runs/current`, and `GET /api/runs/{id}`. `./run_demo.sh` and `make demo` are the terminal path: they start NeMo Gym themselves, write `results/`, and do not serve the page.

Drive the page with Playwright. Confirm side effects with curl. Evidence goes in `.verify-evidence/<timestamp>/`, which is gitignored and is not deleted by cleanup.

## Isolation

The page port is `$PORT` (default 43123, bind `$HOST` or `0.0.0.0`). Two page processes can listen on two ports and both serve Recorded sample, because that mode only reads `sample_run/`.

Live model, and Mock model when `DEMO_SHOW_MOCK=1` or when `POST /api/runs` uses `mode` `mock`, cannot run side by side in one checkout. Both use NeMo Gym on port **11000** and, for mock, the local model on port **43117**. They also rewrite `env.yaml`, `resources_servers/ticketnow_desk/data/tasks.jsonl`, and the generated skill folders. One page process accepts one run at a time. A second `POST /api/runs` while one is `running` returns **409** with `detail.message` and `detail.run`. Run files for a page-started Gym run land in `results/ui/<12-char id>/`. `./run_demo.sh` writes `results/` at the top level and uses the same Gym port, so do not start it while a Gym run from the page is going.

Do not point this skill at the Railway site. A Live run there is a real model call, and this skill must not start one.

## Launch

From the repository root:

```bash
scripts/verify/launch.sh
```

Optional: `VERIFY_PORT=43130 scripts/verify/launch.sh` pins the port. Otherwise the script takes the first free port from 43124 through 43140 so it does not attach to a presenter already on 43123.

On a clean checkout the script creates `.venv` with uv and installs `nemo-gym==0.7.0`, pytest, and pyyaml, the same imports `./run_ui.sh` needs. It then runs `python -m web` with `HOST=127.0.0.1` and the chosen `PORT`. It does not put a key into the environment. The process still loads a repo `.env` if one exists. Leave `DEMO_SHOW_MOCK` unset for the page a presenter sees. The Mock journey needs:

```bash
DEMO_SHOW_MOCK=1 scripts/verify/launch.sh
```

Usable means both of these succeed, not merely that the PID is alive:

- `GET /health` returns `{"status":"ok","service":"ticketnow-it-desk","nemo_gym":"0.7.0"}`
- `GET /api/briefing` returns `modes.recorded.enabled: true`

The script prints the base URL, the PID, and the evidence directory. It records them in `.verify-evidence/<timestamp>/launch.json` and writes that directory path to `.verify-evidence/active`. Server stdout and stderr, including `[gym]` lines once a run starts, go to `server.log` in that directory.

Docker is the packaged form of the same process, not a second app. The image listens on 8080 inside the container:

```bash
docker build -t ticketnow-it-desk .
docker run --name ticketnow-verify --memory=3g --shm-size=64m --cpus=2 -p 43124:8080 ticketnow-it-desk
```

Prefer `scripts/verify/launch.sh` for this skill. It records the PID cleanup is allowed to signal. A container started by hand is outside that record. Stop such a container only with `docker rm -f ticketnow-verify` when that is the name you started.

## Doctor

Read-only. It does not start a run.

```bash
scripts/verify/doctor.sh
```

It reads `.verify-evidence/active` and checks:

- the recorded PID is alive and its command line is `python -m web`
- that PID owns the listening socket for the recorded port
- `/health` is `ticketnow-it-desk` on NeMo Gym `0.7.0`
- `/api/briefing` lists `recorded`, `mock`, and `live`, and whether each is enabled
- whether ports 11000 and 43117 are already taken

The report is printed and saved as `doctor.json` in the evidence directory. Exit code 1 means the server this skill started is not the one answering.

## Drive

Install Playwright once per machine, without downloading a second browser, and use the Chrome already on the machine:

```bash
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --prefix .verify-cache playwright
```

Then, with the server from Launch still up:

```bash
node scripts/verify/drive-mock.mjs
node scripts/verify/drive-selection.mjs
```

The scripts load Playwright from `.verify-cache/node_modules`. Node does not resolve that package through `NODE_PATH` because the drivers are ES modules.

Set `CHROME_PATH` if Chrome is not on `PATH` as `google-chrome`. `drive-mock.mjs` drives the mock feature in `features/mock-run.md` and requires the server from `DEMO_SHOW_MOCK=1 scripts/verify/launch.sh`. It fails when the Mock radio is missing or disabled. `drive-selection.mjs` drives the checkbox columns in `features/skill-selection.md` against the default page, which shows Recorded sample and Live model, and does not start a run.

Other journeys stay in the feature files. Use the same base URL. Real selectors and curl calls:

```bash
BASE=http://127.0.0.1:43124   # the port launch.sh printed

curl -s "$BASE/health"
curl -s "$BASE/api/briefing"
curl -s "$BASE/api/sample"
curl -s "$BASE/api/runs/current"
curl -s "$BASE/api/runs/<id>"
```

Page controls, from `web/static/index.html` and `web/static/app.js`:

| Action | Selector |
| --- | --- |
| Mode | `input[name="mode"][value="recorded"]` or `live`. `mock` is present only when the server was started with `DEMO_SHOW_MOCK=1` |
| Run | `#run-button` |
| Why this mode | `#mode-detail` |
| Playbook checkbox | `#picker input[type="checkbox"][value="security-first-response"]` and the same for `ticket-classification`, `access-request-policy`, `priority-matrix` |
| Matrix column | `#picker label.skill-check.wide input[type="checkbox"]`, explanation `#matrix-why` |
| What will be scored | `.picker-now` |
| Progress | `#progress`, `#progress-list`, `#progress-log` |
| Failure or 409 notice | `#alert` |
| Scores | `#banner strong`, `#comparison .mean b` |
| Ticket card | `#trace button.ticket-card[data-case="offboard-friday"]` |
| Walk step | `#trace [role="tab"]` named `Employee request`, `Skills loaded`, `Agent decision`, `Reward check`, `Score` |
| Next / Back | `#trace .pager button.next`, `#trace .pager button` with text `Back` |
| Skill dialog | `#brief button.textish`, then `#skill-dialog`, `#skill-close` |

`POST /api/runs` body is `{"mode":"mock","skills":["security-first-response","ticket-classification","access-request-policy","priority-matrix"],"compare_without_matrix":true}`. Recorded sample ignores `skills` and always loads `sample_run/`.

## Evidence

`scripts/verify/launch.sh` creates `.verify-evidence/<UTC timestamp>/`. Keep that directory. A proof of the Mock journey contains:

- `01-mock-selected.png` before Run demo, with Mock selected and the four playbooks checked
- `02-running.png` while `#run-button` reads `Running…`
- `03-scores.png` after the banner reads `Mock model`
- `run.json` from `GET /api/runs/{id}`, whose `log_tail` includes `mean/reward`
- `server.log` with `[gym]` lines and `Started a local Ray instance.` The prefix is only on stdout. `log_tail` is the same text without `[gym]`
- `*_aggregate_metrics.json` copied out of `results/ui/<id>/` before cleanup
- `proof.json` with `ok: true`

Standards:

- Drive the control a person uses. A curl that only hits the API does not replace the click for a page feature. Use curl to verify the run JSON, the scores, and the log tail.
- Mock model is the production boundary that replaces the model endpoint with `mock-it-lead` on port 43117. That is the stand-in this repo already ships. Do not add a second fake in front of NeMo Gym.
- Live model calls whatever `POLICY_BASE_URL` points at. Run it only when `POLICY_API_KEY`, `POLICY_BASE_URL`, and `POLICY_MODEL_NAME` are already set on the server and a live call is the thing under test. This skill's drive script never selects Live and never POSTs `{"mode":"live"}`.
- Recorded sample loads `sample_run/` and finishes inside the request. It proves the page, the comparison (means 0.40, 1.00, 0.50 and 0/12, 12/12, 2/12), and Walk the ticket for those three saved configurations. It does not start Ray, does not score a new skill mix, and does not show a `[gym]` log.

## Cleanup

```bash
scripts/verify/cleanup.sh
```

This signals only the PID in the active evidence `server.pid`, and only when `/proc/<pid>/cmdline` is still `python -m web`. It waits for that process to exit so the server can stop the Gym process group it spawned. It then deletes `results/ui/<id>` for the id in `run-id`, deletes `env.yaml` only if launch found no `env.yaml`, and removes `.verify-evidence/active`. It leaves the timestamped evidence directory in place.

Do not `kill` by process name, and do not stop a page that was already listening on 43123.

## Helpers

| Script | Role |
| --- | --- |
| `scripts/verify/launch.sh` | Start the page and wait until `/health` and `/api/briefing` are usable |
| `scripts/verify/doctor.sh` | Read-only identity, port ownership, and mode flags |
| `scripts/verify/drive-mock.mjs` | Playwright drive of the mock skill-checkbox journey. Needs `DEMO_SHOW_MOCK=1` |
| `scripts/verify/drive-selection.mjs` | Playwright drive of the mode picker and checkbox columns. Needs the flag unset |
| `scripts/verify/cleanup.sh` | Stop that PID and drop scratch files |

Feature map: `.cursor/skills/verify-ticketnow/features/README.md`.
