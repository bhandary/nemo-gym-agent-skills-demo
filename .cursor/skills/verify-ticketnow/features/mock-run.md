# Mock run with skill checkboxes

## Sub-features

- Mock model can be selected only when the gym command is installed.
- The four playbook checkboxes choose what is scored: `security-first-response`, `ticket-classification`, `access-request-policy`, `priority-matrix`.
- The extra checkbox, "Also show these tickets with the priority matrix removed", adds the third column when the priority matrix is still selected.
- Run starts NeMo Gym. The progress list updates, and Show technical details holds the last log lines.
- The finished comparison matches the recorded sample for the default selection: 0.40 / 1.00 / 0.50 and 0 of 12, 12 of 12, 2 of 12.

## How to get to it (user POV)

Start the page with `DEMO_SHOW_MOCK=1`. The mode picker then includes Mock model. Choose it. Leave all four playbooks checked and leave the priority-matrix checkbox checked. The line under the checkboxes reads `The comparison shows No skills, All four skills, Without the priority matrix.` Press Run. The button changes to Running…. When the run finishes the banner reads Mock model and the three means match the numbers above.

End state: `GET /api/runs/{id}` has `status` `succeeded` and `mode` `mock`, `log_tail` contains a `mean/reward` line, and `results/ui/<id>/` contains `no_skills_aggregate_metrics.json`, `full_skills_aggregate_metrics.json`, and `without_priority_matrix_aggregate_metrics.json`. The server stdout (`server.log`, and the container stdout on Railway) contains `[gym]` and `Started a local Ray instance.` The `[gym]` prefix is added when the line is copied to stdout. It is not stored in `log_tail`.

## Driving it with Playwright and curl

This is the scripted proof:

```bash
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --prefix .verify-cache playwright
DEMO_SHOW_MOCK=1 scripts/verify/launch.sh
node scripts/verify/drive-mock.mjs
```

Without `DEMO_SHOW_MOCK=1` the Mock radio is absent and the script fails. `POST /api/runs` with `"mode":"mock"` still scores that selection when the radio is hidden. The click journey needs the radio.

The script does the following, and fails closed if any step does not happen:

1. `GET /api/briefing`. If `modes.mock.enabled` is false, write `proof.json` and exit. The reason is `modes.mock.reason`.
2. Open the page. Wait until Recorded sample has painted `#comparison h2` `What the grader awarded`.
3. Check `input[name="mode"][value="mock"]`. If that radio is disabled, fail.
4. Check each `#picker input[type="checkbox"][value="…"]` for the four skill names, and `#picker label.skill-check.wide input[type="checkbox"]`. Require `.picker-now` to name No skills, All four skills, and Without the priority matrix. Save `01-mock-selected.png`.
5. Click `#run-button`. Wait until `#progress` is visible and the button reads `Running…`. Save `02-running.png`.
6. Wait until `#banner strong` is `Mock model` and `#run-button` reads `Run`, or until `#alert h2` is `This run did not finish`. A failure alert fails the journey. Save `03-scores.png`.
7. Require the on-screen means `0.40`, `1.00`, `0.50` and the decision lines `0 of 12 decisions correct`, `12 of 12 decisions correct`, and `2 of 12 decisions correct`.
8. `GET /api/runs/current`, then `GET /api/runs/{id}`. Require the summary rows above and a `mean/reward` line in `log_tail`. Require `[gym]` and `Started a local Ray instance.` in `server.log`. Copy the three aggregate metrics files into the evidence directory.

The same POST, if you need it beside the click:

```bash
curl -s -X POST "$BASE/api/runs" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"mock","skills":["security-first-response","ticket-classification","access-request-policy","priority-matrix"],"compare_without_matrix":true}'
```

Poll `GET /api/runs/{id}` until `status` is `succeeded` or `failed`. Do not treat a still-`running` body as success.

## Gotchas

If `modes.mock.enabled` is false, the radio is disabled and `#mode-detail` shows the reason, usually `The gym command is not installed in this environment. Recorded sample still works.` Fail. Do not click Recorded sample and call that a Mock pass.

The first Mock start on a checkout without `.gym_venvs` installs server environments and can take several minutes. The script waits four minutes. A prepared tree is closer to one minute. Ports 11000 or 43117 already in use fail the run with an error on the page. Free them, or stop the other demo, and run the journey again. Do not raise the wait and ignore the error.

Mock replaces only the model HTTP endpoint. NeMo Gym, Ray, the desk server, and the verifier still run. `[gym]` lines are the evidence that they did.

Unchecking a playbook scores a different mix. The 0.40 / 1.00 / 0.50 end state is for all four playbooks plus the matrix column. A different checkbox set has a different end state and is not a pass for this file.

After this run succeeds, changing a checkbox must leave those three scored columns in place and show `Selection changed - run again to score it`. The caption stays `The comparison shows No skills, All four skills, Without the priority matrix.` until you run again. That check is part of [skill-selection.md](skill-selection.md); this journey stops when the fresh run's columns match the boxes that were checked when Run was pressed.
