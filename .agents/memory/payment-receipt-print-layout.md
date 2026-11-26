---
name: Payment receipt print layout
description: The required paper size and top-aligned sizing behavior for payment receipts.
---

**Rule:** Payment receipts print on portrait US Letter paper and use the full printable width at the top. Compact printed spacing so one concept fits within the upper half-page (accounting for page margins); preserve header typography and the signature block. Additional concept rows grow naturally; do not switch to half-letter paper or vertically center/shrink the receipt.

**Why:** The user approved the top-aligned Letter layout but clarified that a single concept must actually fit in the upper half, with only additional payment rows increasing the required height.

**How to apply:** Keep print page size fixed at Letter and preserve top alignment, width, and visible receipt framing whenever payment receipt styles or print handlers change.
