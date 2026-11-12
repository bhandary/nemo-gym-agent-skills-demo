---
name: ticket-classification
description: Use to set the ticket type, the category, and the assignment group from the ticket record. Load this for every ticket the security playbook did not finish.
metadata:
  version: "1.0.0"
---

# Ticket classification and routing

The employee's message does not name the assignment group. This playbook maps the ticket's category to a group. It does not choose the priority. Priority comes from priority-matrix. Access, joining, and leaving actions come from access-request-policy.

1. Look up the requester and the ticket before you file. Copy `intake_type` to `ticket_type` and copy `category` unchanged, unless access-request-policy replaces them for a joiner or a leaver.
2. The ticket id to look up and to file is the TKT- id in the handoff. Ignore any other number the employee mentions.
3. Map `category` to `assignment_group` with this table. Use the code exactly.

```
group_access: identity-access
group_network: network-ops
group_email: collaboration
group_hardware: endpoint-support
group_software: application-support
group_lifecycle: lifecycle
group_security: security-operations
group_mobile: mobile-devices
group_status: service-desk
```

4. Choose `actions` from the category and the intake type when access-request-policy does not name them. An aged inquiry replaces the inquiry action. That exception is in the priority matrix, not here.

```
action_network_incident: restore_service
action_email_incident: restore_service
action_hardware_incident: dispatch_tech
action_software_incident: restore_service
action_mobile_incident: reset_enrollment
action_software_request: fulfill_catalog
action_inquiry: send_kb
action_request: fulfill_catalog
```

5. Also activate access-request-policy and priority-matrix when they are in the catalog. Read `references/priority-matrix.md` inside priority-matrix before you choose a priority.
6. Call `file_triage` once, after both lookups. Fields are `ticket_id`, `ticket_type`, `category`, `priority`, `assignment_group`, `actions`, and `requester_message`.
7. `actions` is one string of codes separated by commas, alphabetical, with no spaces. `priority` is the code from the priority matrix, unless security-first-response already filed the ticket.
8. `requester_message` is one or two sentences the employee can read. Do not mention internal codes.
9. After `file_triage` succeeds, reply to the teammate with the type, the priority, the assignment group, and the actions. Then stop.
