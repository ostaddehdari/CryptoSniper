from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from apps.trading.models import OrderFill, PaperExitFill, Trade, TradeFinanceEvent

from .invalidation import mark_report_dirty


def _owner_for(instance):
    if isinstance(instance, Trade):
        return instance.owner_id
    if isinstance(instance, (PaperExitFill, TradeFinanceEvent)):
        return instance.trade.owner_id
    if isinstance(instance, OrderFill):
        return instance.order.trade.owner_id
    return None


@receiver(post_save, sender=Trade)
@receiver(pre_delete, sender=Trade)
@receiver(post_save, sender=OrderFill)
@receiver(pre_delete, sender=OrderFill)
@receiver(post_save, sender=PaperExitFill)
@receiver(pre_delete, sender=PaperExitFill)
@receiver(post_save, sender=TradeFinanceEvent)
@receiver(pre_delete, sender=TradeFinanceEvent)
def invalidate_report(sender, instance, **kwargs):
    mark_report_dirty(_owner_for(instance))
