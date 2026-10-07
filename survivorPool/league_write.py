"""Serialize destructive cutover with normal read/validate/write pick requests."""
from contextlib import contextmanager

from django.db import connection, transaction

from .models import Pick


@contextmanager
def pick_write_transaction():
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            name = connection.ops.quote_name(Pick._meta.db_table)
            with connection.cursor() as cursor:
                # Acquire this before reading or validating picks. A cutover's
                # exclusive lock must finish before a queued request sees data.
                cursor.execute(f'LOCK TABLE {name} IN ROW EXCLUSIVE MODE')
        yield


class PickWriteTransactionMixin:
    def post(self, request, *args, **kwargs):
        with pick_write_transaction():
            return super().post(request, *args, **kwargs)
