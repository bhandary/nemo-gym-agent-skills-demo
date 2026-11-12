# TicketNow feature map

Each file is one user-facing journey. Drive it against the page `scripts/verify/launch.sh` started. The end state in the feature file is the pass condition. If a precondition is missing, the journey fails and the reason is stated in Gotchas.

| Feature | File | Proves |
| --- | --- | --- |
| Recorded sample comparison | [recorded-sample.md](recorded-sample.md) | `GET /api/sample` and `POST /api/runs` `mode` `recorded` return means 0.40, 1.00, and 0.50. The page shows that banner only with `DEMO_SHOW_RECORDED=1` |
| Mock run with skill checkboxes | [mock-run.md](mock-run.md) | With `DEMO_SHOW_MOCK=1`, Run starts mock, scores the four playbooks, and the log reaches the page. There is no mode control. `POST /api/runs` with `mode` `mock` still works without the flag |
| Playbook checkbox columns | [skill-selection.md](skill-selection.md) | The table, summary, caption, and walk follow the checked playbooks |
| Live run gating | [live-gating.md](live-gating.md) | Live stays off until the server already has `POLICY_*` |
| Walk the ticket | [walk-the-ticket.md](walk-the-ticket.md) | Five steps for one ticket, with Pass and Miss on the filing |
| Run already in progress | [run-in-progress.md](run-in-progress.md) | A second start attaches to the current run with HTTP 409 |

Scripted proofs: [mock-run.md](mock-run.md) via `DEMO_SHOW_MOCK=1 scripts/verify/launch.sh` and `node scripts/verify/drive-mock.mjs`, and [skill-selection.md](skill-selection.md) via `node scripts/verify/drive-selection.mjs` with `DEMO_SHOW_MOCK` and `DEMO_SHOW_RECORDED` unset.
