---
name: close-the-ticket
description: Use to finish a ticket. It says which lookups must happen before filing, and the exact fields file_resolution expects.
metadata:
  version: "1.0.0"
---

# Close the ticket

1. Call lookup_order with the order id from the customer's message, and lookup_ticket with the ticket id, before you call file_resolution. Do this even when an escalation or refund skill already told you the outcome.
2. Call file_resolution once, after the lookups. Use the disposition, refund amount, and escalate flag from the skill that matched. Do not guess a shorter code.
3. file_resolution takes ticket_id, disposition, refund_usd, escalate, and customer_message.
4. refund_usd is a number. Use 0 when nothing is refunded. escalate is a boolean.
5. customer_message is one or two sentences the customer could read. Do not mention internal disposition codes.
6. After file_resolution succeeds, reply to the teammate with the disposition, the refund amount, and whether you escalated. Then stop.
