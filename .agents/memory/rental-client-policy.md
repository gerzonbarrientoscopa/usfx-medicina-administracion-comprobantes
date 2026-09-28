---
name: Cross-office rental clients
description: Why students can rent at another office but cross-office lookup needs exact identifiers
---

**Rule:** A student can rent an environment outside their enrollment office without being duplicated as a Persona. For non-superadmins, cross-office student discovery and booking require an exact C.I. or C.U.; partial name search remains scoped to their own office.

**Why:** Persona and Estudiante identities are mutually exclusive, so forcing a second Persona record would block legitimate rentals. Broad cross-office student searches would expose unnecessary identity data to cashiers.

**How to apply:** Preserve both the exact-match search restriction and the server-side document check when changing rental client selection; avoid broadening the regular student-management scope.