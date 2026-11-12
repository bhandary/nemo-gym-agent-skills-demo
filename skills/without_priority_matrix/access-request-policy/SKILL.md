---
name: access-request-policy
description: Use when someone needs access, is joining, or is leaving. It names the approval and the same-day offboarding work. It does not choose the priority.
metadata:
  version: "1.0.0"
---

# Access request policy

Run this after security-first-response has ruled the ticket out, together with ticket-classification. This skill names actions. It does not name the priority and it does not name the assignment group. The group still comes from the category table in ticket-classification. The priority still comes from the priority matrix.

1. Look up the requester and read `employment`. Look up the ticket and read `intake_type` and `category`.
2. If `category` is `lifecycle` and `employment` is `leaving` or `left`, file ticket type `request`, category `lifecycle`, and the offboarding actions below. Do not also ask for an approval. The priority is the offboarding row in the priority matrix.
3. If `category` is `lifecycle` and `employment` is `new_hire`, file ticket type `request`, category `lifecycle`, and the onboarding actions below. The priority is the onboarding row in the priority matrix.
4. If `category` is `access` and `intake_type` is `request`, the only action is the approval below. GitHub, Jira, a distribution list, a shared mailbox, and admin rights all use this action. Keep the ticket type and category from the ticket.
5. If `category` is `access` and `intake_type` is `incident`, the only action is the credential reset below. A forgotten password, a lockout, or a new phone that broke sign-in is this case, not an access request.
6. Otherwise this skill adds no action. Use ticket-classification.

```
offboard_employment: leaving,left
offboard_actions: collect_equipment,disable_same_day
onboard_employment: new_hire
onboard_actions: provision_accounts,provision_equipment
access_request_action: manager_approval
access_incident_action: reset_credentials
```
