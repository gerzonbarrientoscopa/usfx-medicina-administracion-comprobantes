---
name: Revenue catalog scope
description: Ownership and uniqueness rules for budget classifiers and revenue concepts.
---

Budget classifiers are shared across all offices and managed globally. Revenue concepts belong to one office; concept names may repeat between offices, but every five-digit concept code is globally unique.

**Why:** the user confirmed that classifier and concept ownership differ, that concept names may repeat across offices, and that concept codes must be unique across the whole system.

**How to apply:** Keep classifiers global and concepts office-scoped. Enforce concept-code uniqueness globally in each backend and database schema; keep name uniqueness office-scoped.
