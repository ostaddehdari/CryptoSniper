from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Q

from .aggregation import rebuild_user_reports


@shared_task(name="reports.rebuild_user", acks_late=True, time_limit=120)
def rebuild_user(user_id):
    return rebuild_user_reports(user_id)


@shared_task(name="reports.refresh_aggregates", acks_late=True, time_limit=300)
def refresh_aggregates():
    results = []
    users = (
        get_user_model()
        .objects.filter(is_active=True)
        .filter(Q(report_refresh__dirty_at__isnull=False) | Q(report_refresh__isnull=True))
    )
    for user_id in users.values_list("pk", flat=True):
        results.append(rebuild_user_reports(user_id))
    return {"users": len(results), "rows": sum(item["rows"] for item in results)}
