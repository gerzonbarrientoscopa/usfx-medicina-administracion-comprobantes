---
name: Institutional access constraints
description: Local access flow for the institution-owned authentication link.
---

The institution's authentication page is outside the project's control and sends only `cu`, `nu`, `hu`, and `iu`. The requested local flow matches `cu` against a CU assigned to a local user and accepts `hu` only within 60 seconds, interpreted as seconds since midnight UTC. Keep the existing login page unchanged. If any institutional parameters are present but authentication fails, show a dedicated expired/unauthorized state instead of the login form. Local role and office remain authoritative; do not grant permissions from `nu` or `iu`. The SuperAdmin account must retain password login and may also use the institutional link if a CU is assigned.

**Why:** The user stated they cannot change the institutional page or exchange data with its authentication system, asked for access based on the provided URL fields, and required failed parameterized links not to fall through to login. Recent `hu` values aligned with UTC, while Bolivia-time validation rejected them.

**How to apply:** Treat CU-link access as a bearer-identifier convenience flow, not a cryptographically verified SSO assertion. Explain this limitation when changing or deploying the flow; never imply the bare URL parameters prove who issued them.
