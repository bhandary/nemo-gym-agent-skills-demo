# Playbook checkbox columns

## Sub-features

- Four playbook checkboxes and the box "Also show these tickets with the priority matrix removed".
- The caption `.picker-now` lists the same names as the score-table column headers, in the same order.
- Recorded sample keeps a column only when that column is one of No skills, All four skills, or Without the priority matrix and the checkboxes would score that same mix.
- Mock and Live, before a run, preview every column the next run will score. A column the sample did not score says Not scored yet.
- After a Mock or Live run, the columns stay the ones that run scored. A later checkbox change shows `Selection changed - run again to score it` and does not rename those columns.
- With every playbook unchecked, the only column is No skills. With the priority matrix unchecked, the matrix comparison box is disabled and `#matrix-why` explains why.

## How to get to it (user POV)

Open the briefing page. The panel is Playbooks the lead may open. Leave all four playbooks checked and leave the matrix comparison checked. The caption reads `The comparison shows No skills, All four skills, Without the priority matrix.` and the table has those three columns, with means 0.40, 1.00, and 0.50.

Uncheck Access request policy. The table keeps No skills only. Above the means, the page says `Not in the recorded sample - run Mock or Live to score it`. The recorded Without the priority matrix scores are not left on screen under a new name.

Uncheck the remaining playbooks. The caption reads `The comparison shows No skills.` and there is no missing-mix note, because that column is the recorded sample. The matrix comparison box is disabled, and the line under it says the priority matrix is not selected, so there is no matrix column to remove.

Check every playbook except Priority matrix. The columns are No skills and Without the priority matrix, means 0.40 and 0.50. The matrix box stays disabled.

Choose Mock model, check every playbook except Access request policy, and leave the matrix comparison on. The headers are No skills, Without Access request policy, and Without the priority matrix. No skills still shows 0.40 from the sample. The other two say Not scored yet. Do not press Run demo for this journey.

End state: `.picker-now` equals `The comparison shows ` plus the column headers joined by commas. The Agent decision step of Walk the ticket uses those same card titles.

## Driving it with Playwright and curl

```bash
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --prefix .verify-cache playwright
node scripts/verify/drive-selection.mjs
```

The script saves `01-all-four.png`, `02-without-access.png`, `03-no-skills.png`, `04-matrix-off.png`, and `05-mock-preview.png` in the evidence directory. It fails if a header list and `.picker-now` disagree, if unchecking Access request policy still shows All four skills or Without the priority matrix on Recorded sample, or if the Mock preview fills Without the priority matrix with the recorded 0.50.

Selectors: `#picker input[type="checkbox"][value="access-request-policy"]`, the same pattern for the other three names, `#picker label.skill-check.wide input[type="checkbox"]`, `#matrix-why`, `#comparison [role="columnheader"]`, `#comparison .column-note`, `#comparison .mean b`, `#trace [role="tab"]` named Agent decision, and `#trace .compare-card h3`.

This journey does not POST `/api/runs`. The mapping the POST will use is `run_plan` in `demo/skill_sets.py`: No skills, the selected mix, and Without the priority matrix only when the matrix playbook is selected and the comparison box is on. A two-playbook selection that still includes the matrix uses a separate folder, `skills/selection_without_matrix`, so the ablation does not overwrite `skills/selected`.

## Gotchas

The column header is visually uppercase. Read `textContent`, not the rendered CSS text, when comparing it with the caption.

Recorded sample has no column for Without Access request policy. Showing the recorded Without the priority matrix scores in its place is the bug this journey rejects. If that header remains after Access request policy is unchecked, the journey fails.

The matrix comparison box stays checked in memory when the priority matrix playbook is turned off, and it comes back when that playbook is checked again. While the playbook is off the box is disabled and it does not add a column. If `#matrix-why` is missing, the journey fails.

Mock preview still shows recorded numbers for a column whose id is in `sample_run` (No skills, All four skills, Without the priority matrix). A different mix must say Not scored yet. Do not press Run demo to hide a wrong recorded number.
