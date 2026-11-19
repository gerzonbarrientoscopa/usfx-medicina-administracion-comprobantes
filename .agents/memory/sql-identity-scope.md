---
name: Fresh SQL identity scope
description: Fresh databases and generated identities separate from user codes.
---

The current user decision is to use **new databases**, not migrate old data, and to generate Id in both backends for Clients and Users. User Código is separate from the generated Id. MongoDB retains UUID identities; SQL uses generated numeric identities.

For institutional student search, map the API's `idpersona` value into the client's C.I. field, but never use it as the local client Id.

**Why:** The user chose generated local identities instead of using user Código as SQL's primary key, and explicitly requested that the academic API's `idpersona` map to C.I.

**How to apply:** Never use an API-provided Id or user Código as the local primary key. Map student `idpersona` to C.I. while generating a separate client Id. Preserve the common frontend contract with string Id representations. SQL recreation remains local to the user; do not automatically wipe data on application startup.
