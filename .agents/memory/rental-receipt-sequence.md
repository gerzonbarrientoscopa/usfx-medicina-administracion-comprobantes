---
name: Shared receipt sequence
description: Why rental and student payment receipts use an append-only shared counter
---

**Rule:** Never rewind a receipt counter when a payment draft is discarded or a rental payment fails. Gaps are acceptable; reusing a number is not.

**Why:** A rental may have allocated a number but not yet persisted its paid state while another payment draft is deleted. Rewinding based only on visible receipts can issue that number again across the two receipt collections.

**How to apply:** Preserve monotonic allocation and only reconcile counters upward. When changing either payment flow, test a concurrent rental allocation and student-payment draft deletion together.