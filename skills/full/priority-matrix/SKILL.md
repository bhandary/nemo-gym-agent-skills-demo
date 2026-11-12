---
name: priority-matrix
description: Use to choose the priority after the type and the actions are known. The levels and the hour threshold are only in the reference file. Load this before you file, unless the security playbook already set the priority.
metadata:
  version: "1.0.0"
---

# Priority and SLA

This skill chooses `priority`. It does not choose the assignment group.

1. Activate this skill, then read `references/priority-matrix.md` before you file. The priority codes and the hour threshold live only in that file.
2. Use the ticket and requester facts, not the wording of the message. A message that says "three days" is not the threshold. Compare `hours_open` on the ticket to the threshold in the matrix.
3. Apply the first matching row in the matrix. security-first-response already files the priority-one security incidents. Do not reopen those.
4. An aged inquiry changes the priority and replaces the inquiry action with the aged action from the matrix.
