# TicketNow feature map

Each file is one user-facing journey. Drive it against the page `scripts/verify/launch.sh` started. The end state in the feature file is the pass condition. If a precondition is missing, the journey fails and the reason is stated in Gotchas.

| Feature | File | Proves |
| --- | --- | --- |
| Recorded sample comparison | [recorded-sample.md](recorded-sample.md) | The page loads `sample_run` with means 0.40, 1.00, and 0.50 |
| Mock run with skill checkboxes | [mock-run.md](mock-run.md) | Mock scores the four playbooks, and the log reaches the page |
| Live run gating | [live-gating.md](live-gating.md) | Live stays off until the server already has `POLICY_*` |
| Walk the ticket | [walk-the-ticket.md](walk-the-ticket.md) | Five steps for one ticket, with Pass and Miss on the filing |
| Run already in progress | [run-in-progress.md](run-in-progress.md) | A second start attaches to the current run with HTTP 409 |

The scripted proof for this skill is [mock-run.md](mock-run.md), via `node scripts/verify/drive-mock.mjs`.
