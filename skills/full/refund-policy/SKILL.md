---
name: refund-policy
description: Use when a customer wants money back, a replacement, or a return of merchandise. Load this before choosing a refund disposition or a refund amount.
metadata:
  version: "1.0.0"
---

# Refund policy

This skill decides ordinary refunds. It does not decide safety cases or merchandise above the high-value line. Those belong to escalation-playbook, which you apply first.

1. Activate this skill, then read `references/rate-card.md` before you choose an amount or a disposition. The numbers and the disposition codes live only in that file.
2. Look up the order and the ticket first. The rate card applies to the facts those tools return, not to the customer's wording.
3. Shipping is never part of the refund. Use the merchandise amount from the order.
4. If the order is unopened and the delivery is still inside the unopened window on the rate card, refund the full merchandise amount and use the full-refund disposition from the rate card. Do not escalate.
5. If the order was opened, the order says damage happened in transit, and delivery is still inside the damage window on the rate card, refund the damage percent from the rate card and use the partial disposition. Round money to the nearest cent, half up. Do not escalate.
6. If neither window applies and the customer tier is gold, refund nothing and use the gold disposition from the rate card. Do not escalate.
7. Otherwise refund nothing and use the standard denial disposition from the rate card. Do not escalate.
8. File the resolution with close-the-ticket. The customer message may explain the outcome in plain language. It must not invent a different amount.
