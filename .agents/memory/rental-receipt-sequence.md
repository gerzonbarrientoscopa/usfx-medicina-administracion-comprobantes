---
name: Shared receipt sequence
description: Why rental and student payment receipts use an append-only shared counter
---

**Rule:** A discarded student-payment draft may return its number only if an atomic compare-and-decrement confirms it is still the latest shared allocation. Never rewind past a newer receipt; failed rental payments keep their allocated number consumed. Legacy year-only counters can seed office-scoped counters upward, but the legacy document stays untouched.

**Why:** Student payments and rentals share one counter per office/year. A newer allocation may be in flight and not yet visible in its receipt collection, so reading existing receipts and setting the counter backward can issue duplicates. The old year-only counter format is not read by current allocation code; ignoring it could make a new office counter restart below existing allocations.

**How to apply:** Reclaim a draft's number only with an atomic `seq == draft_code` condition after deletion. Migrate any legacy year-only high-water mark to each office's scoped counter with `$max`, then reconcile against extant receipts without reducing values. Test tail reuse during a rental allocation, deletion of an older draft after a newer receipt, and legacy counter migration.