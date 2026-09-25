---
name: Dev-domain Python TLS
description: Certificate verification behavior when testing this app's development URL from shell Python.
---

Python `requests` from the workspace rejected the HTTPS certificate at the development proxy, although the app and browser preview were healthy.

**Why:** A development API smoke test initially failed during TLS negotiation, before reaching the endpoint. This is not evidence that the application route is broken.

**How to apply:** For development-only smoke tests, use the local workflow port or disable certificate verification only in the throwaway test request. Never disable TLS verification in application code or production calls.