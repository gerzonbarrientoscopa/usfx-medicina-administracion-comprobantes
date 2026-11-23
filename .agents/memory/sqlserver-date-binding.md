---
name: SQL Server date parameter binding
description: Avoid language-dependent conversion errors when sending date filters to SQL Server.
---

Pass parsed Python `date` values as ODBC parameters when filtering SQL Server `date` or datetime columns. Avoid passing `YYYY-MM-DD` strings for implicit conversion, since SQL Server session language/date format can cause an out-of-range conversion error.

**Why:** The SQL Server reporting endpoint failed to convert ISO-looking text to `datetime` under the active session format.

**How to apply:** Parse and validate incoming dates once, bind those typed values in queries, and format as ISO text only for API output.
