# Error monitoring

Application errors go to console output (Replit deployment logs), with timestamp,
severity, logger, traceback, and command/season/week for staff operations. Caught
operation errors and failed odds refreshes are logged; odds failures exit nonzero.
Expected command refusals are warnings, not crash alerts.

## Production activation

1. Set `SENTRY_DSN` in Replit deployment secrets for the team's Sentry project.
2. Set `SENTRY_ENVIRONMENT=production` and `SENTRY_RELEASE` to the deployed Git SHA.
3. In Sentry, create an issue alert for new and regressed errors in production and
   select an actual recipient or team. Configure a rate alert for repeated errors.
4. Verify a controlled test event arrives with the correct release/environment and
   that its alert reaches the recipient. Do not assume a configured DSN proves delivery.

Without a DSN, console logging works but no remote Sentry alerts are sent. This
repository cannot verify deployment secrets, Sentry project permissions or alert
delivery. Alert activation is a deployment task, not completed by merging code.

## Privacy and investigation

Sentry captures no request bodies or stack-frame locals. The before-send hook
removes request headers, cookies, query strings and user identity. Known application
secret values and HTTP URL queries are redacted in console messages and Sentry
events. Do not put user content, passwords, tokens or API response bodies in log
messages; automatic redaction is not a substitute for that rule.

Start with the Sentry stack, release and timestamp. Correlate staff-operation events
with command, season and week in Replit logs. Fix and deploy with a new release SHA
so regressions can be distinguished from older events. Console logs remain the
fallback if Sentry delivery fails.

This covers Python/Django failures, including caught staff-operation errors. It
does not detect browser-only JavaScript errors, total site outages, or a weekly job
that never runs. Browser telemetry, external uptime checks and scheduled-job
check-ins require separately configured monitoring; CI browser tests remain the
current browser regression coverage.

SDK options: https://docs.sentry.io/platforms/python/configuration/options/
