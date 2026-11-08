import io
import json
import logging
from unittest.mock import patch

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import path

from survivor.request_logging import ServerErrorFormatter


def broken_page(request):
    try:
        raise ConnectionError('private-db-host password=not-for-logs')
    except ConnectionError as cause:
        raise RuntimeError('private-form-value') from cause


def explicit_error(request):
    return HttpResponse(status=500)


def healthy_page(request):
    return HttpResponse('OK')


urlpatterns = [
    path('broken/', broken_page),
    path('explicit/', explicit_error),
    path('healthy/', healthy_page),
]


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=['testserver'],
    ROOT_URLCONF=__name__,
    MIDDLEWARE=['survivor.request_logging.RequestDiagnosticsMiddleware'],
)
class RequestLoggingTests(SimpleTestCase):
    def test_configured_handler_emits_json_for_production_errors(self):
        self.client.raise_request_exception = False
        logger = logging.getLogger('django.request')
        self.assertFalse(logger.propagate)
        handler = next(
            handler for handler in logger.handlers
            if isinstance(handler.formatter, ServerErrorFormatter)
        )
        output = io.StringIO()
        with patch.object(handler, 'stream', output):
            response = self.client.get('/broken/')
        entries = output.getvalue().splitlines()
        self.assertEqual(len(entries), 1)
        data = json.loads(entries[0])
        self.assertEqual(data['request_id'], response['X-Request-ID'])
        self.assertEqual(data['exceptions'][0]['type'], 'builtins.RuntimeError')

    def test_exception_contains_correlation_and_stack_but_no_sensitive_values(self):
        self.client.raise_request_exception = False
        self.client.cookies['sessionid'] = 'private-session-cookie'
        with self.assertLogs('django.request', level='ERROR') as captured:
            response = self.client.post(
                '/broken/?token=private-query-token',
                {'password': 'private-submitted-password'},
                HTTP_AUTHORIZATION='Bearer private-auth-token',
                HTTP_X_REQUEST_ID='untrusted-request-id',
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(captured.records), 1)
        rendered = ServerErrorFormatter().format(captured.records[0])
        data = json.loads(rendered)
        self.assertEqual(data['request_id'], response['X-Request-ID'])
        self.assertEqual(len(data['request_id']), 32)
        self.assertEqual(data['route'], 'broken/')
        self.assertEqual(data['method'], 'POST')
        self.assertEqual(data['status'], 500)
        self.assertGreaterEqual(data['duration_ms'], 0)
        self.assertGreaterEqual(data['process_age_seconds'], 0)
        self.assertGreater(data['process_id'], 0)
        self.assertEqual(
            [entry['type'] for entry in data['exceptions']],
            ['builtins.RuntimeError', 'builtins.ConnectionError'],
        )
        self.assertTrue(any(
            frame['function'] == 'broken_page'
            for frame in data['exceptions'][0]['frames']
        ))
        for secret in (
            'private-db-host', 'not-for-logs', 'private-form-value',
            'private-session-cookie', 'private-query-token',
            'private-submitted-password', 'private-auth-token', 'untrusted-request-id',
        ):
            self.assertNotIn(secret, rendered)

    def test_explicit_500_without_exception_is_logged(self):
        with self.assertLogs('django.request', level='ERROR') as captured:
            response = self.client.get('/explicit/')
        data = json.loads(ServerErrorFormatter().format(captured.records[0]))
        self.assertEqual(data['status'], 500)
        self.assertEqual(data['request_id'], response['X-Request-ID'])
        self.assertNotIn('exceptions', data)

    def test_success_does_not_emit_error_and_request_ids_are_unique(self):
        with patch.object(logging.getLogger('django.request'), 'error') as error:
            first = self.client.get('/healthy/')
            second = self.client.get('/healthy/')
        error.assert_not_called()
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first['X-Request-ID'], second['X-Request-ID'])
