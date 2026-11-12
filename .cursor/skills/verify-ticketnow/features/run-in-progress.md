# Run already in progress

## Sub-features

- Recorded sample finishes inside the POST, so it does not stay `running`.
- Mock model and Live model stay `running` until NeMo Gym finishes or fails.
- A second POST while one run is `running` returns HTTP 409. The body is `{"detail":{"message":"A run is already in progress. Showing it.","run":{...}}}`.
- The page adopts `detail.run` and shows an alert instead of starting a second Gym.

## How to get to it (user POV)

Start a Mock run as in the Mock journey, and while the button still says Running… press Run demo again. The page does not start a second score. The alert heading is `A run is already in progress` and the text is `Showing it. The scores update here when it finishes.` The progress list keeps the same steps.

End state: the second response is status 409, `detail.run.id` equals `GET /api/runs/current`'s running id, `detail.run.status` is `running`, and `#alert h2` reads `A run is already in progress`.

## Driving it with Playwright and curl

Start Mock from the page (see [mock-run.md](mock-run.md)) and wait until `#run-button` reads `Running…`. Then:

```bash
curl -s -D - -o "$EVIDENCE/second-post.json" -X POST "$BASE/api/runs" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"mock","skills":["security-first-response","ticket-classification","access-request-policy","priority-matrix"],"compare_without_matrix":true}'
```

Require `HTTP/1.1 409`, `detail.message` equal to `A run is already in progress. Showing it.`, and `detail.run.id` equal to the id already on screen. `GET /api/runs/current` returns that same id with `status` `running`.

In Playwright, click `#run-button` again while it reads `Running…`. The button is disabled during a run, so the click is not how the page sends the second POST. The control that represents a second start is a second client: curl, or a second browser context that loads the page and clicks `#run-button` while the first run is still going. After that second context clicks, its `#alert h2` reads `A run is already in progress`.

Leave the original run in place until it reaches `succeeded` or `failed`. Then clean it up with `scripts/verify/cleanup.sh`. Do not kill the Gym process by name.

## Gotchas

FastAPI nests the payload under `detail`. A check that looks for a top-level `message` or `run` fails even when the page handled the 409 correctly.

Recorded sample cannot produce this state. The POST returns the finished run. If you need a 409 and Mock is disabled, the journey fails. The reason is `modes.mock.reason`. Do not pretend a finished recorded POST is a conflict.

Two page processes do not share the in-memory run list. A 409 from one port says nothing about a server on another port. They still share ports 11000 and 43117, so the second process's Mock run fails at Gym startup instead of returning 409.

Do not produce this state by POSTing to the Railway deployment.
