---
name: security-first-response
description: Use on every ticket before the other playbooks. It catches security signals that must go to the security team immediately, ahead of ordinary routing.
metadata:
  version: "1.0.0"
---

# Security first response

Check this playbook before ticket-classification, access-request-policy, and priority-matrix. If a rule here matches, file that decision and stop. Do not apply the other playbooks.

1. Look up the requester and the ticket before you file. The employee's story is not enough. The security signal is a field on the ticket.
2. Read `security_signal`. If it is one of the signals below, this is a priority-one security incident. File it and stop. A lost or stolen laptop and a clicked suspicious link are this case even when the message sounds like a hardware problem.
3. Use these values exactly. `actions` is already alphabetical, with no spaces.

```
p1_signals: phishing_click,lost_or_stolen,account_compromise
p1_type: incident
p1_category: security
p1_priority: P1
p1_group: security-operations
action_phishing_click: isolate_session,reset_credentials
action_lost_or_stolen: remote_wipe,reset_credentials
action_account_compromise: isolate_session,preserve_mailbox
```

4. Call `file_triage` with `ticket_id`, `ticket_type`, `category`, `priority`, `assignment_group`, `actions`, and `requester_message`. Copy the codes above for the matching signal. `requester_message` is one or two sentences the employee can read. Do not mention internal codes.
5. If `security_signal` is `none` or anything else, do not file from this skill. Activate ticket-classification, access-request-policy, and priority-matrix, and read the priority matrix, before you file.
