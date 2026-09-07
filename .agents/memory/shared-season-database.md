---
name: Shared season database
description: Safety constraint for maintenance commands and league-data changes.
---

Development and production currently receive the same shared Neon database
secret, so management commands run in the workspace can affect live league
data.

**Why:** A cleanup initially targeted Replit's built-in development database,
but the Django app actually used shared Neon. Data maintenance must target the
database Django is actively connected to, and should be treated as a production
operation.

**How to apply:** Before any cleanup, seed, schedule sync, odds refresh, or
winner update, inspect and count the affected Django ORM records. State the
production impact explicitly and verify counts after the command.