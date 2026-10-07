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
production impact explicitly and verify counts after the command. Browser and
automated tests must explicitly clear the inherited Neon URL before supplying a
local test database; otherwise Django's URL precedence connects the test seeder
to the shared league database. Replit Publish schema validation is separate: it
diffs the managed development database against managed production, so a Django
migration against Neon does not update the schema Publish introspects.

Schema-dependent code must not be left running while its migration is pending.
Django's development server reloads edited Python immediately.

**Why:** During an additive feature build, the running leaderboard began querying
a new column before its migration was applied, causing a missing-column error.

**How to apply:** Coordinate additive migrations with the running server early
in the build, or pause the server until code and schema are compatible. Verify
existing league records remain unchanged; never run a cutover or seeder merely
to make the new schema usable.