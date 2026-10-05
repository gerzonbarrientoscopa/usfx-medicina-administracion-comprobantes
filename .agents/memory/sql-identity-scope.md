---
name: Fresh SQL identity scope
description: User decisions about SQL recreation, entered user IDs, and the shared frontend contract.
---

The user selected **“Recrear la base desde cero”**, not migration of existing SQL UUIDs, and **“El ID del usuario”** for the three-digit code entered through user CRUD. MongoDB must retain its UUID identifiers.

**Why:** These were explicit user choices when offered data preservation versus database recreation, and a separate user code versus the primary key.

**How to apply:** Do not reintroduce implicit UUID migration or change Mongo primary keys. SQL recreation is performed on the user's local machine, not automatically against a database from Replit. Preserve the shared frontend's JSON contract even when physical SQL names change.

SQL user codes must not be reassigned to another person while historical receipts still refer to their original owner.

**Why:** Unlike UUIDs, manually entered three-digit IDs can be reused; doing so would attribute past receipts to the wrong person.

**How to apply:** Preserve historical identity when changing user deletion or primary-key behavior.
