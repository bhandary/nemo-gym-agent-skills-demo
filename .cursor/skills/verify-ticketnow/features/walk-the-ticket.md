# Walk the ticket

## Sub-features

- Twelve ticket cards, each with a type badge (Incident, Request, or Inquiry), a title, a category, and a ticket id.
- A five-step stepper: Employee request, Skills loaded, Agent decision, Reward check, Score.
- Next, Back, and the left and right arrow keys move one step.
- Agent decision and Score show Without skills beside the selected playbooks, with the words Pass and Miss on each check.
- Show technical details is closed until it is opened. It holds the tool list, and after a Gym run, the NeMo Gym log.

## How to get to it (user POV)

The walk sits under the score table, headed Walk the ticket. The Friday offboard card is selected when the page loads (`offboard-friday`, TKT-2408). Click that card if another ticket is selected. Step 1 shows the employee note and the company rule. Click Next through Skills loaded, Agent decision, and Reward check. On Score, the left column is Without skills and the right column is All four skills when every playbook is checked. The big scores are 0.4 and 1.0. Pass and Miss are written on the checks, not only drawn in color.

End state on the recorded sample, all four playbooks checked, ticket `offboard-friday`, step Score: `#trace .walk-kicker` reads `Step 5 of 5`, the two `.compare-card h3` titles are `Without skills` and `All four skills`, `.big-score` reads `0.4` and `1.0`, and at least one `.mark.pass` and one `.mark.fail` are visible with the text Pass and Miss. `#trace details.technical` is not open.

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

A playbook mix that is not in the view on screen has no right-hand trace. The card says `This side was not scored in the run on screen. Run Mock or Live to score it.` That is a failed walk for this file when the claim was the recorded offboard comparison. Restore all four checkboxes. The recorded sample has no other mixes.

Clicking a ticket card resets the walk to step 1. Arrow keys do not move the walk while a skill dialog is open (`#skill-dialog`) or while a checkbox has focus.

Recorded sample is enough for this end state. A Mock run that has not finished still shows the previous view, dimmed, until `status` is `succeeded`. Do not read Score off a dimmed table and call the new run verified.
