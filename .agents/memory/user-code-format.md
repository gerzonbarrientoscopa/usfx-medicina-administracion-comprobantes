---
name: User code format
description: Product rules for assigning and validating user codes.
---

User codes have exactly three ASCII alphanumeric characters; they may contain letters and do not have to be numeric-only. `000` remains reserved for the bootstrap SuperAdmin.

**Why:** The user clarified that three-character user codes can be alphanumeric.

**How to apply:** Keep this rule consistent in the user interface, API validation, directory imports, and both database schemas.
