---
name: Rental booking consistency
description: Why occupancy must be retained on uncertain booking writes and provisional records block edits
---

**Rule:** Treat room occupancy as protected until a provisional booking is confirmed or its cancellation is known to have committed. Never free a slot merely because a database call raised after an unknown write outcome.

**Why:** This project's MongoDB runs without multi-document transactions. A delayed insert or a confirmation that commits but loses its response can otherwise leave two active rentals for the same interval or an active rental with no occupied slot.

**How to apply:** Preserve provisional booking states during room schedule changes and recovery; clean only stale claims with a verified cancellation. Test delayed inserts and commit-then-error failures whenever booking persistence changes.