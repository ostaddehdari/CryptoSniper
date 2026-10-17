from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.audit import record_audit
from apps.marketdata.feeds import get_quote

from .engine import condition, metric_for
from .models import PriceAlert


@transaction.atomic
def save_alert(owner, form):
    draft = form.save(commit=False)
    if draft.pk:
        current = PriceAlert.objects.select_for_update().get(pk=draft.pk, owner=owner)
        if form.cleaned_data["version"] != current.version:
            raise ValidationError("هشدار تغییر کرده؛ صفحه را تازه کنید.")
        draft.version = current.version + 1
    elif PriceAlert.objects.filter(owner=owner).count() >= 200:
        raise ValidationError("حداکثر ۲۰۰ هشدار برای هر کاربر مجاز است.")
    draft.owner = owner
    quote = get_quote(draft.market)
    if draft.trade and draft.trade.protection.paper_scenario:
        p = draft.trade.protection
        if p.last_tick_at and p.last_price:
            quote = {
                "price": str(p.last_price),
                "observed_at": p.last_tick_at.isoformat(),
                "source": "paper_scenario",
                "stale": (timezone.now() - p.last_tick_at).total_seconds() > 25,
            }
    if not quote or quote["stale"]:
        raise ValidationError(
            "قیمت تازه لازم است؛ قیمت بازار را در واچ‌لیست به‌روز کنید. "
            "در سناریوی Paper ابتدا Tick تازه ثبت کنید."
        )
    from decimal import Decimal

    draft.reference_price = Decimal(quote["price"])
    draft.reference_at = parse_datetime(quote["observed_at"])
    draft.reference_source = quote["source"]
    draft.last_observed_at = draft.reference_at
    metric, _ = metric_for(draft, draft.reference_price)
    draft.last_metric = metric
    draft.armed = metric is None or not condition(draft, metric)
    draft.status = "watching" if draft.enabled else "disabled"
    draft.save()
    record_audit(
        "alerts.saved", user=owner, metadata={"alert_id": draft.pk, "version": draft.version}
    )
    return draft
