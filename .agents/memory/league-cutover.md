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

The user says red cells represent losses and green cells represent wins.
Biggest-favorite losses need a manual override because that classification is
not recorded in the sheet.

**Why:** The user supplied these spreadsheet interpretation requirements.

**How to apply:** Preserve Excel cell colors when reading the cutover file and
provide an explicit staff correction for biggest-favorite loss classification;
do not infer that classification solely from the result color.

Imported historical outcomes and manual biggest-favorite classifications are
authoritative history, not values to recompute from later odds or results feeds.

**Why:** The spreadsheet runs the real league, while the app's automated data
and pilot history may disagree with it.

**How to apply:** Preserve imported history through routine results posting and
odds refreshes. Staff classification corrections should be explicit and audited.
