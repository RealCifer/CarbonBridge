"""
carbonbridge/celery.py
======================
Celery application instance for CarbonBridge.

Start worker:
    celery -A carbonbridge worker --loglevel=info

Start beat scheduler (periodic tasks):
    celery -A carbonbridge beat --loglevel=info
"""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carbonbridge.settings")

app = Celery("carbonbridge")

# Load celery settings from Django settings using the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all INSTALLED_APPS
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
