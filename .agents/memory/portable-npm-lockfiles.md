---
name: Portable npm lockfiles
description: Prevent CI failures caused by environment-specific package registry URLs.
---

Committed npm lockfiles must not contain Replit-internal package firewall URLs.
Use public npm registry URLs so GitHub Actions and other external runners can
complete clean installs.

**Why:** Installing a dependency inside Replit wrote an internal hostname into
the lockfile. The package worked in the workspace but `npm ci` failed in GitHub
Actions because that hostname is not publicly resolvable.

**How to apply:** After changing Node dependencies, scan the lockfile for
internal registry hostnames and validate with a clean `npm ci`.