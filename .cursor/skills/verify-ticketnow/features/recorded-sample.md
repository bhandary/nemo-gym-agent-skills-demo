# Recorded sample comparison

## Sub-features

- `GET /api/sample` and `POST /api/runs` with `mode` `recorded` return the twelve TicketNow tickets. The page has no control for this mode.
- With `DEMO_SHOW_RECORDED=1`, the page shows that sample. The banner reads Recorded sample. The score table has three columns: No skills, All four skills, Without the priority matrix.
- Means are 0.40, 1.00, and 0.50. Correct decisions are 0 of 12, 12 of 12, and 2 of 12.
- On that flagged page, unchecking a playbook that is not one of those three mixes drops that mix from the table. The page says `Not in the recorded sample - run Live to score it`. It does not keep a recorded column whose skill set is different from the checkboxes.
- Without the flag, the page does not say Recorded sample. Columns the sample already scored still show those numbers as a preview of what Run will score. Run itself starts live.

## How to get to it (user POV)

There is no mode picker. For the saved sample on screen, start the page with `DEMO_SHOW_RECORDED=1`. The banner reads Recorded sample and names mock-it-lead. No Run click is required. Changing a playbook checkbox only filters this saved run. Run still starts live, so do not press it for this journey.

Without the flag, prove the sample from the API. `GET /api/sample` and `POST /api/runs` with `{"mode":"recorded"}` return the same view.

End state with the flag: `#banner strong` is `Recorded sample`, `#comparison .mean b` reads `0.40`, `1.00`, `0.50`. Either way, `GET /api/sample` returns those means for `no_skills`, `full_skills`, and `without_priority_matrix`.

## Driving it with Playwright and curl

```bash
BASE=http://127.0.0.1:43124   # port from scripts/verify/launch.sh
curl -s "$BASE/api/sample"
```

The `comparison.summary` rows must be mean reward 0.4, 1.0, and 0.5 with correct counts 0, 12, and 2, each out of 12.

In Playwright, with `DEMO_SHOW_RECORDED=1`, open `BASE` and wait for `#comparison h2` with text `What the grader awarded` and `#banner strong` with text `Recorded sample`. There is no `#modes` and no `input[name="mode"]`. Read `#comparison .mean b`. With every playbook checkbox still checked, `.picker-now` includes `No skills`, `All four skills`, and `Without the priority matrix`.

To see the missing-mix message on that flagged page, uncheck `#picker input[type="checkbox"][value="access-request-policy"]`. The only column header left beside Ticket is `No skills`, `.picker-now` reads `The comparison shows No skills.`, and `#comparison .column-note` reads `Not in the recorded sample - run Live to score it`. The recorded Without the priority matrix column is not a stand-in for that mix. Check the box again before treating the 0.40 / 1.00 / 0.50 table as the result.

Without the flag, the same uncheck keeps three columns. The two the sample did not score say Not scored yet. That is the default page, covered by [skill-selection.md](skill-selection.md).

## Gotchas

Recorded sample does not start NeMo Gym, Ray, or the mock model. `server.log` gains no `[gym]` lines from this journey, and ports 11000 and 43117 stay closed. A missing `sample_run/manifest.json` makes `modes.recorded.enabled` false and `GET /api/sample` return 404. The page then shows `The scores could not be loaded.` Fail the journey. Do not substitute a hand-written score file.

The checkbox filter hides columns. It does not re-score. Passing this journey does not prove Mock or Live.
