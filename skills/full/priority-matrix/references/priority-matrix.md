# TicketNow priority matrix

Apply the first matching row after security-first-response. Do not reprioritize a ticket that playbook already filed.

A phishing click, a lost or stolen laptop, and a compromised account are P1. They go to the security team immediately. security-first-response files those. The signals are `phishing_click`, `lost_or_stolen`, and `account_compromise`. Leave that filing alone.

```
offboard_priority: P2
onboard_priority: P3
outage_priority: P2
incident_priority: P3
request_priority: P4
inquiry_priority: P4
aged_inquiry_hours: 72
aged_inquiry_priority: P2
aged_inquiry_action: status_update
```

Rows, in order:

1. If the requester's employment is leaving or left and the category is lifecycle, priority is offboard_priority. Same-day disable is the reason. The actions still come from access-request-policy.
2. If the requester's employment is new_hire and the category is lifecycle, priority is onboard_priority.
3. If the ticket's shared_outage is true, priority is outage_priority. One person reporting a slow connection is still a site incident when monitoring says the outage is shared.
4. If intake_type is incident, priority is incident_priority.
5. If intake_type is request, priority is request_priority.
6. If intake_type is inquiry and hours_open is greater than or equal to aged_inquiry_hours, priority is aged_inquiry_priority and the action becomes aged_inquiry_action instead of the ordinary inquiry action.
7. Otherwise an inquiry uses inquiry_priority and keeps the ordinary inquiry action from ticket-classification.

Worked example, not a live ticket: an inquiry open 90 hours uses P2 and the action status_update. An inquiry open 5 hours uses P4 and keeps send_kb. A shared outage uses P2 even when the message sounds like one person. A lifecycle leaver uses P2. A lifecycle new hire uses P3. An ordinary request uses P4.
