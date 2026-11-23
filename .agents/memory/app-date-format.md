---
name: Interface date format
description: The display and entry convention for dates throughout this application.
---

All dates entered or displayed in the application UI use `dd/mm/yyyy`. Keep API and storage dates in ISO `YYYY-MM-DD` form.

**Why:** The user requested this format across every interface where dates are entered or shown.

**How to apply:** Use the shared date input and formatting helpers for forms, tables, reports, and printed outputs; convert to ISO at API boundaries.
