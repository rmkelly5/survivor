import io
import logging
import os
import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase
import requests
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from survivor.observability import SafeFormatter, before_send


class PrivacyTests(SimpleTestCase):
    def test_error_log_reaches_sentry_without_request_body_or_locals(self):
        events = []

        class OfflineTransport(Transport):
            def capture_envelope(self, envelope):
                for item in envelope.items:
                    if item.headers.get('type') == 'event':
                        events.append(item.payload.json)

        # A local transport proves SDK capture without sending a real alert.
        with sentry_sdk.init(
            dsn='https://public@example.com/1', transport=OfflineTransport(),
            default_integrations=False,
            integrations=[LoggingIntegration(event_level=logging.ERROR)],
            include_local_variables=False, max_request_body_size='never',
            send_default_pii=False, before_send=before_send,
        ):
            try:
                private_form_value = uuid.uuid4().hex
                raise RuntimeError('test operation failed')
            except RuntimeError:
                logging.getLogger('survivorPool.capture_test').exception('Operation failed')
        self.assertEqual(len(events), 1)
        self.assertIn('RuntimeError', str(events[0]))
        self.assertNotIn(private_form_value, str(events[0]))
        self.assertNotIn('vars', events[0]['exception']['values'][0]['stacktrace']['frames'][0])

    @patch.dict(os.environ, {'ODDS_API_KEY': 'test-private-key'})
    def test_console_traceback_redacts_credentials(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SafeFormatter('%(message)s'))
        logger = logging.Logger('privacy-test')
        logger.addHandler(handler)
        try:
            raise RuntimeError('https://example.com/odds?apiKey=test-private-key')
        except RuntimeError:
            logger.exception('Refresh failed')
        output = stream.getvalue()
        self.assertIn('RuntimeError', output)
        self.assertIn('Refresh failed', output)
        self.assertNotIn('test-private-key', output)
        self.assertNotIn('apiKey=', output)

    def test_sentry_removes_private_request_fields_and_user(self):
        event = {'request': {'url': 'https://example.com/pick?token=secret',
                             'data': {'password': 'secret'}, 'cookies': 'secret',
                             'headers': {'Authorization': 'secret'},
                             'query_string': 'token=secret', 'env': {'REMOTE_ADDR': 'private'}},
                 'user': {'email': 'private@example.com'},
                 'exception': {'values': [{'type': 'RuntimeError', 'value': 'failed'}]}}
        result = before_send(event, {})
        self.assertNotIn('secret', str(result))
        self.assertNotIn('user', result)
        self.assertEqual(set(result['request']), {'url'})
        self.assertEqual(result['exception']['values'][0]['type'], 'RuntimeError')

    @patch.dict(os.environ, {'ODDS_API_KEY': 'test-private-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups',
           side_effect=requests.Timeout('upstream timed out'))
    def test_odds_failure_logs_and_fails_command(self, matchups):
        with self.assertLogs('survivorPool.management.commands.fetch_nfl_odds', level='ERROR') as logs:
            with self.assertRaisesMessage(CommandError, 'Odds refresh failed'):
                call_command('fetch_nfl_odds', week=3, year=2026)
        self.assertEqual(len(logs.records), 1)
        self.assertIsNotNone(logs.records[0].exc_info)
        self.assertIn('week=3', logs.output[0])


class OperationLoggingTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user('operator', is_staff=True))

    @patch('survivorPool.views.call_command', side_effect=RuntimeError('private upstream payload'))
    def test_caught_failure_has_traceback_and_safe_response(self, command):
        with self.assertLogs('survivorPool.views', level='ERROR') as logs:
            response = self.client.post('/league-operations/', {'action': 'schedule', 'week': 3})
        self.assertEqual(response.context['command_status'], 'error')
        self.assertNotContains(response, 'private upstream payload')
        self.assertIn('command=fetch_nfl_schedule', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    @patch('survivorPool.views.call_command', side_effect=CommandError('Week still open'))
    def test_expected_refusal_is_warning_not_crash(self, command):
        with self.assertLogs('survivorPool.views', level='WARNING') as logs:
            response = self.client.post('/league-operations/', {'action': 'results', 'week': 3})
        self.assertEqual(response.context['command_status'], 'error')
        self.assertEqual(logs.records[0].levelno, logging.WARNING)
        self.assertIsNone(logs.records[0].exc_info)
