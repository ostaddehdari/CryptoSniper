"""Deterministic Margin ledger for Paper simulation only."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import PaperMarginLoan, Trade, TradeEvent, TradeFinanceEvent


@transaction.atomic
def create_margin_loan(trade_id):
    trade = (
        Trade.objects.select_for_update()
        .select_related("market__base_asset", "market__quote_asset", "account__exchange")
        .get(pk=trade_id)
    )
    if trade.market.market_type != "margin":
        return None, False
    if trade.mode != "paper" or trade.account.exchange.adapter_code != "simulator":
        raise ValidationError("وام Margin فقط در شبیه‌ساز Paper مجاز است.")
    leverage = Decimal(str(trade.snapshot.get("leverage", "1")))
    if leverage <= 1 or leverage > trade.market.max_leverage:
        raise ValidationError("اهرم Margin برای شبیه‌ساز معتبر نیست.")
    if trade.side == "buy":
        asset = trade.market.quote_asset
        principal = trade.quantity * trade.entry_price * (Decimal(1) - Decimal(1) / leverage)
    else:
        asset = trade.market.base_asset
        principal = trade.quantity
    loan, created = PaperMarginLoan.objects.get_or_create(
        trade=trade,
        defaults={"account": trade.account, "asset": asset, "principal": principal},
    )
    if created:
        TradeEvent.objects.create(
            trade=trade,
            event_type="PAPER_MARGIN_BORROWED",
            payload={"asset": asset.symbol, "principal": str(principal)},
        )
    return loan, created


@transaction.atomic
def accrue_margin_interest(trade_id, *, hours):
    hours = Decimal(str(hours))
    if not hours.is_finite() or hours <= 0:
        raise ValidationError("مدت بهره Margin باید مثبت باشد.")
    loan = (
        PaperMarginLoan.objects.select_for_update().select_related("trade").get(trade_id=trade_id)
    )
    if loan.state != PaperMarginLoan.State.ACTIVE:
        return Decimal(0)
    amount = (loan.principal * loan.hourly_rate * hours).quantize(Decimal("0.0000000000000001"))
    loan.accrued_interest += amount
    loan.save(update_fields=("accrued_interest",))
    return amount


@transaction.atomic
def repay_margin_loan(trade_id):
    loan = (
        PaperMarginLoan.objects.select_for_update()
        .select_related("trade", "asset")
        .filter(trade_id=trade_id)
        .first()
    )
    if not loan or loan.state == PaperMarginLoan.State.REPAID:
        return loan, False
    total = loan.principal + loan.accrued_interest
    quote_rate = (
        loan.trade.entry_price if loan.asset_id == loan.trade.market.base_asset_id else Decimal(1)
    )
    if loan.accrued_interest:
        TradeFinanceEvent.objects.create(
            trade=loan.trade,
            asset=loan.asset,
            kind=TradeFinanceEvent.Kind.BORROW_INTEREST,
            amount=loan.accrued_interest,
            quote_rate=quote_rate,
            provider_reference=f"paper-margin:{loan.pk}:interest",
            occurred_at=timezone.now(),
        )
    TradeFinanceEvent.objects.create(
        trade=loan.trade,
        asset=loan.asset,
        kind=TradeFinanceEvent.Kind.REPAYMENT,
        amount=loan.principal,
        quote_rate=quote_rate,
        provider_reference=f"paper-margin:{loan.pk}:principal",
        occurred_at=timezone.now(),
    )
    loan.repaid_amount = total
    loan.state = PaperMarginLoan.State.REPAID
    loan.repaid_at = timezone.now()
    loan.save(update_fields=("repaid_amount", "state", "repaid_at"))
    TradeEvent.objects.create(
        trade=loan.trade,
        event_type="PAPER_MARGIN_REPAID",
        payload={"asset": loan.asset.symbol, "total": str(total)},
    )
    return loan, True
