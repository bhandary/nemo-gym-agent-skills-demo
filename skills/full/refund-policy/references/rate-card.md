# Northwind refund rate card

Read these values exactly. Do not round the windows, and do not refund shipping.

```
unopened_full_refund_days: 30
opened_damage_days: 14
opened_damage_refund_percent: 70
full_refund_disposition: full_refund_unopened
partial_refund_disposition: damage_window_partial
gold_no_refund_disposition: goodwill_replacement
standard_no_refund_disposition: deny_outside_window
refund_basis: merchandise_only
```

Worked example, not a live ticket: an opened, damage-in-transit order of $50 in merchandise, delivered 10 days ago, is inside the damage window. The refund is 70 percent of $50, which is $35.00, disposition damage_window_partial, and escalate is false. Shipping on that order is not refunded.

Gold customers outside both windows get goodwill_replacement and a refund of 0. Standard customers outside both windows get deny_outside_window and a refund of 0.
