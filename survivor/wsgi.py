"""
WSGI config for survivor project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'survivor.settings')

try:
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
except Exception as exc:
    print(f"\n=== WSGI STARTUP FAILED ===", file=sys.stderr)
    print(f"Exception type: {type(exc).__name__}", file=sys.stderr)
    print(f"Exception message: {exc}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print(f"=== END WSGI ERROR ===\n", file=sys.stderr)
    raise
