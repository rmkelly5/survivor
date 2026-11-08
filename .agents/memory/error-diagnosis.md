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
