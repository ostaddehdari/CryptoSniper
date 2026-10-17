from celery.signals import before_task_publish
from django.utils import timezone


@before_task_publish.connect
def stamp_message(headers=None, **kwargs):
    if headers is not None:
        headers["sent_at"] = timezone.now().isoformat()
