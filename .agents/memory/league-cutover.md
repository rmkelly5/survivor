---
name: League cutover
description: Pilot status and the source of authoritative league history before cutover.
---

The app is in pilot mode. The current league is run through Google Sheets, and
the user intends to cut over by having a staff user upload the spreadsheet and
replace the app's existing picks with the sheet's picks.

**Why:** The user stated that Google Sheets is the current league system; pilot
picks in the app should not take precedence over that history.

**How to apply:** Treat the sheet as the intended source of truth when designing
the cutover import. This does not authorize immediate deletion or an import
without validation and explicit confirmation.
