---
name: Fresh SQL identity scope
description: Fresh databases and generated identities separate from user codes.
---

The current user decision is to use **new databases**, not migrate old data, and to generate Id in both backends for Clients and Users. User Código is separate from the generated Id. MongoDB retains UUID identities; SQL uses generated numeric identities.

**Why:** The user changed the earlier decision that SQL user Código was the primary key while requesting unified Clients and selectable API imports.

**How to apply:** Never use an API-provided Id or user Código as the local primary key. Preserve the common frontend contract with string Id representations. SQL recreation remains local to the user; do not automatically wipe data on application startup.
