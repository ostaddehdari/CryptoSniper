from django.db.models import F
from django.utils import timezone

from .models import ReportRefreshState


def mark_report_dirty(owner_id):
    if not owner_id:
        return
    state, created = ReportRefreshState.objects.get_or_create(
        owner_id=owner_id, defaults={"dirty_at": timezone.now()}
    )
    if not created:
        ReportRefreshState.objects.filter(pk=state.pk).update(
            source_version=F("source_version") + 1, dirty_at=timezone.now()
        )
