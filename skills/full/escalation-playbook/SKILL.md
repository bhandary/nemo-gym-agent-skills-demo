---
name: escalation-playbook
description: Use on every ticket before the refund skill. It catches safety flags and high-value merchandise, which a refund rule must not override.
metadata:
  version: "1.0.0"
---

# Escalation playbook

Check this playbook before you apply refund-policy. If a rule here matches, stop. Do not also apply the refund skill.

1. Look up the ticket and the order. The customer's story is not enough.
2. If the ticket's safety_flag is true, a person takes the case. File refund 0, escalate true, and this disposition:

```
safety_flag_disposition: escalate_safety
```

3. If the order's merchandise amount is above this line, a person takes the case even when the goods are unopened and still inside a refund window. File refund 0, escalate true, and this disposition:

```
high_value_merchandise_usd: 200
high_value_disposition: escalate_high_value
```

4. Compare the merchandise amount to 200 using greater-than. An amount of 200 itself is not high value.
5. If neither rule matches, leave this skill and use refund-policy for the amount and the disposition.
