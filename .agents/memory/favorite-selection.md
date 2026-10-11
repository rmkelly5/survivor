---
name: Biggest-favorite league rule
description: Spread-based selection, tied favorites, and safe activation during a week.
---

Choose the biggest favorite(s) by the largest point spread given to the opponent,
not by moneyline odds. Preserve explicit historical loss classifications.

**Why:** The user specified that spreads, rather than odds to win, determine the
league's biggest favorite.

**How to apply:** Keep the pick-page banner and automatic loss-fee calculation
consistent. Include all favorites tied on spread; do not fall back to moneylines
when a spread is unavailable.

Favorite selection and automatic contributions are calculated when pages load.
Changing that rule can affect displayed contributions using existing odds even
without an odds refresh or a database write.

**Why:** The user approved proceeding midweek without running odds again, but
that alone does not freeze read-time calculations.

**How to apply:** Do not run odds refreshes or recalculations against live data
unless requested. Explain read-time effects rather than promising that skipping
an odds refresh preserves current displayed fees.
