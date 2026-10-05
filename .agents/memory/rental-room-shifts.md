---
name: Room rental shifts
description: Product rules for configurable room shifts, fixed tariffs, and booking history.
---

Every rental environment configures distinct, nonoverlapping morning, afternoon, and night hours. Weekly availability still controls which dates and blocks can be booked. Fixed tariffs and new bookings use the environment's current shift hours, while existing rentals retain the exact intervals recorded when they were created. The agenda distinguishes pending reservations from paid bookings.

**Why:** This is the user's requested behavior for room rentals; changing an environment's shift hours must not rewrite existing rental records.

**How to apply:** Keep the shift configuration and its validation consistent across MongoDB and SQL Server, and keep historical rental intervals independent from later environment changes.
