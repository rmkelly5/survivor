"""Request correlation and privacy-conscious server-error diagnostics."""

import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone


PROCESS_STARTED = time.monotonic()


class RequestDiagnosticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Generate our own ID rather than trusting arbitrary incoming headers.
        request.diagnostic_id = uuid.uuid4().hex
        request.diagnostic_started = time.monotonic()
        response = self.get_response(request)
        response['X-Request-ID'] = request.diagnostic_id
        return response


class ServerErrorFormatter(logging.Formatter):
    """Do not serialize Django's request object, SQL, exception values or locals."""

    def format(self, record):
        request = getattr(record, 'request', None)
        started = getattr(request, 'diagnostic_started', None)
        match = getattr(request, 'resolver_match', None)
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level': record.levelname,
            'event': 'django_server_error',
            'request_id': getattr(request, 'diagnostic_id', None),
            'method': getattr(request, 'method', None),
            # A route pattern identifies the page without URL values or queries.
            'route': getattr(match, 'route', None) or '<unresolved>',
            'status': getattr(record, 'status_code', None),
            'duration_ms': round((time.monotonic() - started) * 1000, 1)
            if started is not None else None,
            'process_id': os.getpid(),
            'process_age_seconds': round(time.monotonic() - PROCESS_STARTED, 1),
        }
        if record.exc_info and record.exc_info[1] is not None:
            # Include chained exception types and stack locations, but not their
            # messages: DB errors can contain SQL values or connection details.
            exceptions = []
            exception = record.exc_info[1]
            seen = set()
            while exception is not None and id(exception) not in seen:
                seen.add(id(exception))
                exceptions.append({
                    'type': f'{type(exception).__module__}.{type(exception).__name__}',
                    'frames': [
                        {'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
                        for frame in traceback.extract_tb(exception.__traceback__)
                    ],
                })
                exception = exception.__cause__ or (
                    None if exception.__suppress_context__ else exception.__context__
                )
            payload['exceptions'] = exceptions
        return json.dumps(payload)
