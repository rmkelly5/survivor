from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from django.conf import settings
from django.db.utils import ConnectionHandler


class ConnectionHealthTests(TestCase):
    def test_url_database_configuration_enables_health_checks(self):
        # Test execution uses an explicit isolated SQLite DATABASE_URL.
        self.assertTrue(settings.DATABASES['default']['CONN_HEALTH_CHECKS'])
        self.assertEqual(settings.DATABASES['default']['CONN_MAX_AGE'], 600)

    def test_stale_connection_is_replaced_before_query(self):
        with TemporaryDirectory() as directory:
            databases = ConnectionHandler({
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': str(Path(directory) / 'connection-test.sqlite3'),
                    'CONN_HEALTH_CHECKS': True,
                    'CONN_MAX_AGE': 600,
                },
            })
            connection = databases['default']
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    self.assertEqual(cursor.fetchone(), (1,))
                old_connection = connection.connection
                # Emulate the server closing a connection while Django retains it.
                old_connection.close()
                # Django calls this at request boundaries, resetting its health check.
                connection.close_if_unusable_or_obsolete()
                # SQLite's is_usable() always returns True; simulate the failed
                # probe PostgreSQL performs, exercising Django's reconnect path.
                with patch.object(connection, 'is_usable', return_value=False) as check:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT 2')
                        self.assertEqual(cursor.fetchone(), (2,))
                    check.assert_called_once()
                self.assertIsNot(connection.connection, old_connection)
            finally:
                connection.close()

    def test_healthy_connection_is_reused_and_checked_once_per_request(self):
        with TemporaryDirectory() as directory:
            databases = ConnectionHandler({
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': str(Path(directory) / 'connection-test.sqlite3'),
                    'CONN_HEALTH_CHECKS': True,
                    'CONN_MAX_AGE': 600,
                },
            })
            connection = databases['default']
            try:
                connection.ensure_connection()
                original = connection.connection
                connection.close_if_unusable_or_obsolete()
                with patch.object(connection, 'is_usable', wraps=connection.is_usable) as check:
                    for _ in range(2):
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT 1')
                    self.assertEqual(check.call_count, 1)
                    connection.close_if_unusable_or_obsolete()
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT 1')
                    self.assertEqual(check.call_count, 2)
                self.assertIs(connection.connection, original)
            finally:
                connection.close()
