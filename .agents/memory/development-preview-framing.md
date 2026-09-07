---
name: Development Preview framing
description: Replit Preview iframe requirement and production framing boundary.
---

Allow cross-origin iframe rendering when Django is running in development, but
keep framing denied in production.

**Why:** The Django server and public development URL both returned HTTP 200,
yet Replit Preview showed an unreachable-app message because
`X-Frame-Options: DENY` prevented the proxy page from embedding the app.

**How to apply:** Preserve development-only iframe permission alongside the
existing development cookie settings. Verify the actual `.replit.dev` response
headers when Preview fails; a successful localhost request does not prove the
iframe can render. Also keep a single web port mapping: an unused second port
can leave the Preview pane targeting a dead service even while port 5000 is
healthy.