---
name: Client deletion integrity
description: Why client deletion protection cannot expire while reference writes have uncertain outcomes.
---

**Rule:** Coordinate deletion and reference-changing writes through MongoDB, not process-local locks. Never expire deletion protection solely because a worker or database request timed out. Keep protection after a dispatched insert, reassignment, or delete whose outcome is uncertain.

**Why:** A write can finish after the HTTP request has failed or a worker has paused. Removing its protection based on an empty reference query or a timeout can allow deletion followed by a late payment/reservation insert, leaving an orphan. A stalled deletion can likewise finish after a new reference write if its gate is reopened.

**How to apply:** Client protection is global across offices because the catalog is shared, while authorization for financial documents remains office-scoped. Release normal successful operations and pre-write validation failures; retain uncertain operations conservatively. Any future abandoned-operation recovery must establish that the old write can no longer commit before unblocking deletion, rather than merely checking age or current references.
