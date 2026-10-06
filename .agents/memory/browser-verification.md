---
name: Browser verification
description: Distinguishing a shell browser test harness failure from an application failure.
---

Do not change the app solely because an ad-hoc browser harness reports a timeout. Independently inspect whether the target page rendered before treating the timeout as an application bug. A rendered parent may still hide controls behind prerequisites; CDP `Runtime.evaluate` executes in the browser page, not shell Node.

**Why:** The shell Node runtime lacked native WebSocket support, and an initial CDP harness timed out while an independent probe found the login form. Correcting the harness let authenticated client and role checks pass without application changes.

**How to apply:** Verify the runtime's browser dependencies, select a page target explicitly, and handle the CDP response envelope consistently. Inspect which controls are actually mounted before clicking them; a Node-context failure in the test harness is not an app failure. Use a real login against the running backend for permission checks, not an authentication bypass.
