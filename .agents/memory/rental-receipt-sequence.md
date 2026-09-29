---
name: Shared receipt sequence
description: Why rental and student payment receipts use an append-only shared counter
---

**Rule:** A discarded student-payment draft may return its number only if an atomic compare-and-decrement confirms it is still the latest shared allocation. Never rewind past a newer receipt; failed rental payments keep their allocated number consumed.

**Why:** Student payments and rentals share one counter per office/year. A newer allocation may be in flight and not yet visible in its receipt collection, so reading existing receipts and setting the counter backward can issue duplicates.

**How to apply:** Reclaim a draft's number only with an atomic `seq == draft_code` condition after deletion. Keep startup reconciliation upward-only, and test both tail reuse during a rental allocation and deletion of an older draft after a newer receipt.