"""Shared privacy safeguards for console logs and Sentry error events."""

import logging
import os
import re


def redact(text):
    # HTTP exceptions can include the Odds API key or database credentials in URLs.
    for name in ('ODDS_API_KEY', 'DJANGO_SECRET_KEY', 'DATABASE_URL',
                 'NEON_DATABASE_URL', 'RESEND_API_KEY', 'SENTRY_DSN'):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, '[Filtered]')
    return re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[Filtered]', text)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def before_send(event, hint):
    # Keep the stack and operational tags, not form contents, cookies or identities.
    request = event.get('request', {})
    for key in ('data', 'cookies', 'headers', 'query_string', 'env'):
        request.pop(key, None)
    event.pop('user', None)

    def clean(value):
        if isinstance(value, str):
            return redact(value)
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(event)
