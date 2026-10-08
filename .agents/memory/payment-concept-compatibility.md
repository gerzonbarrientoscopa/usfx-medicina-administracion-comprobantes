---
name: Payment concept compatibility
description: User-selected scope for removing the redundant payment-level concept.
---

For itemized payments, stop storing the duplicate payment-level `id_tipo_pago`. Keep legacy reads, searches and editing for receipts without items. Do not remove the API input, the item-derived response, the SQL column or legacy index as part of this change.

**Why:** The user chose “dejar de guardar la copia” rather than a destructive migration and reported that all current payments have this field NULL. That database claim was not independently verified.

**How to apply:** Use payment items as the concept source for new itemized receipts. Retain the old field only as the source for genuine legacy receipts without items; a full legacy/schema removal requires a separate user decision.
