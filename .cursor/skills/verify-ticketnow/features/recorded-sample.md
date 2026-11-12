# Recorded sample comparison

## Sub-features

- The page opens on Recorded sample and shows the twelve TicketNow tickets.
- The score table has three columns: No skills, All four skills, Without the priority matrix.
- Means are 0.40, 1.00, and 0.50. Correct decisions are 0 of 12, 12 of 12, and 2 of 12.
- Unchecking a playbook that is not one of those three mixes drops that mix from the table. The page says `Not in the recorded sample - run Live to score it`. It does not keep a recorded column whose skill set is different from the checkboxes.

## How to get to it (user POV)

Open the briefing page. Leave the selected mode on Recorded sample. The banner reads Recorded sample and names mock-it-lead. The comparison is already on the page. No Run demo click is required for this journey. Changing a playbook checkbox only filters this saved run.

End state: `#banner strong` is `Recorded sample`, `#comparison .mean b` reads `0.40`, `1.00`, `0.50`, and `GET /api/sample` returns the same means for `no_skills`, `full_skills`, and `without_priority_matrix`.

## Driving it with Playwright and curl

```bash
BASE=http://127.0.0.1:43124   # port from scripts/verify/launch.sh
curl -s "$BASE/api/sample"
```

The `comparison.summary` rows must be mean reward 0.4, 1.0, and 0.5 with correct counts 0, 12, and 2, each out of 12.

In Playwright, open `BASE` and wait for `#comparison h2` with text `What the grader awarded` and `#banner strong` with text `Recorded sample`. Read `#comparison .mean b`. With every playbook checkbox still checked, `.picker-now` includes `No skills`, `All four skills`, and `Without the priority matrix`.

To see the missing-mix message, uncheck `#picker input[type="checkbox"][value="access-request-policy"]`. The only column header left beside Ticket is `No skills`, `.picker-now` reads `The comparison shows No skills.`, and `#comparison .column-note` reads `Not in the recorded sample - run Live to score it`. The recorded Without the priority matrix column is not a stand-in for that mix. Check the box again before treating the 0.40 / 1.00 / 0.50 table as the result.

## Gotchas

Recorded sample does not start NeMo Gym, Ray, or the mock model. `server.log` gains no `[gym]` lines from this journey, and ports 11000 and 43117 stay closed. A missing `sample_run/manifest.json` makes `modes.recorded.enabled` false and `GET /api/sample` return 404. The page then shows `The scores could not be loaded.` Fail the journey. Do not substitute a hand-written score file.

The checkbox filter hides columns. It does not re-score. Passing this journey does not prove Mock or Live.
