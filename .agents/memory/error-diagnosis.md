---
name: Error diagnosis
description: Evidence-first scope for investigating intermittent return-visit server errors.
---

For unexplained first-return server errors that disappear after refreshing,
add diagnostic logging rather than speculative connection or infrastructure changes.

**Why:** The user said, "If you do not already know how to fix then our only option is to add logging."

**How to apply:** Establish the exception or other concrete cause before proposing
a corrective change. Do not treat cold-start timing or stale-connection hypotheses
as a confirmed diagnosis.

The user clarified that errors occur when revisiting the site in an existing
window; refreshing or opening a new window fixes it. The whole page shows the
error on the home page, not just chat.

**Why:** This is the reported reproduction pattern, not a confirmed root cause.

**How to apply:** Distinguish a restored tab or background-request failure from
a full-page navigation error before attributing the problem to database reuse.
Do not present chat polling failures as the explanation for this reported
full-page home error.
