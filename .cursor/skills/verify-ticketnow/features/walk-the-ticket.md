# Walk the ticket

## Sub-features

- Twelve ticket cards, each with a type badge (Incident, Request, or Inquiry), a title, a category, and a ticket id.
- A five-step stepper: Employee request, Skills loaded, Agent decision, Reward check, Score.
- Next, Back, and the left and right arrow keys move one step.
- Agent decision and Score show one card per column on the score table. The card title is that column's name. Pass and Miss are written on each check.
- Show technical details is closed until it is opened. It holds the tool list, and after a Gym run, the NeMo Gym log.

## How to get to it (user POV)

The walk sits under the score table, headed Walk the ticket. The Friday offboard card is selected when the page loads (`offboard-friday`, TKT-2408). Click that card if another ticket is selected. Step 1 shows the employee note and the company rule. Click Next through Skills loaded, Agent decision, and Reward check. On Score, the cards use the same names as the table columns. With every playbook checked, those names are No skills, All four skills, and Without the priority matrix. The big scores include 0.4 and 1.0. Pass and Miss are written on the checks, not only drawn in color.

End state on the recorded sample, all four playbooks checked and the matrix comparison checked, ticket `offboard-friday`, step Score: `#trace .walk-kicker` reads `Step 5 of 5`, the `.compare-card h3` titles are `No skills`, `All four skills`, and `Without the priority matrix`, `.big-score` includes `0.4` and `1.0`, and at least one `.mark.pass` and one `.mark.fail` are visible with the text Pass and Miss. `#trace details.technical` is not open.

## Driving it with Playwright and curl

Open the page and wait for `#trace h2` with text `Walk the ticket`.

```text
#trace button.ticket-card[data-case="offboard-friday"]
#trace [role="tab"][aria-selected="true"]
#trace .pager button.next
#trace .pager button >> text=Back
```

Click the offboard card. Its `aria-pressed` becomes `true`. Click `#trace .pager button.next` four times, or click the tab whose text is `Score`. Assert the end state above. Press ArrowLeft once and assert `.walk-kicker` reads `Step 4 of 5`. The arrow keys are ignored while focus is in an input, so click the walk card before sending the key.

`GET /api/sample` is the data behind this walk. The offboard ticket's full-skills reward is 1 and the no-skills reward is 0.4. If those rows are absent, the on-screen scores will not match and the journey fails.

`?ticket=offboard-friday&step=5` opens on that step. Use it only to confirm the deep link. The journey itself clicks the card and Next.

## Gotchas

A column the saved sample did not score has no trace, and the card says `Not scored yet`. With `DEMO_SHOW_RECORDED=1` the score table instead drops that mix and says `Not in the recorded sample - run Live to score it`. That is a failed walk for this file when the claim was the saved offboard comparison. Restore all four checkboxes. The saved sample has no other mixes.

Clicking a ticket card resets the walk to step 1. Arrow keys do not move the walk while a skill dialog is open (`#skill-dialog`) or while a checkbox has focus.

The saved sample is enough for this end state on the default page, because those three columns are already in `sample_run`. A run that has not finished still shows the previous view, dimmed, until `status` is `succeeded`. Do not read Score off a dimmed table and call the new run verified.
