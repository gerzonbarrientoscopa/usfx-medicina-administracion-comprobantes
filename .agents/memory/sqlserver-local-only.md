---
name: SQL Server local-only workflow
description: The user reserves the SQL Server backend for execution and validation on their own computer.
---

Do not import, execute, test, or connect to `backend/serverSQL.py` from the Replit workspace unless the user explicitly changes this instruction.

**Why:** The user stated they will use this backend on their local machine and prohibited testing or database connections from this workspace.

**How to apply:** Make requested source edits, inspect the diff, and limit verification to static checks and unrelated frontend/server.py checks. Never restart a workflow that launches `serverSQL.py`.