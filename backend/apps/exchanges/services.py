import hashlib
import re

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from .adapters import AdapterError, get_adapter
from .models import Asset, BalanceSnapshot, ExchangeMarket, UserExchangeAccount
from .security import get_account_credentials

SAFE_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,60}$")


def _credentials_for(account):
    if not account.credentials_encrypted:
        return {}
    return get_account_credentials(account)


def permission_payload(report):
    reference_hint = ""
    if report.account_reference:
        reference_hint = hashlib.sha256(report.account_reference.encode()).hexdigest()[:12]
    return {
        "can_read": report.can_read,
        "can_trade_spot": report.can_trade_spot,
        "can_trade_margin": report.can_trade_margin,
        "can_withdraw": report.can_withdraw,
        "ip_restricted": report.ip_restricted,
        "account_reference_hash": reference_hint,
        "notes": [str(note)[:160] for note in report.notes[:10]],
    }


def _error_code(error):
    provider_code = str(error).strip().lower()
    if SAFE_ERROR_CODE.fullmatch(provider_code):
        return provider_code
    return str(getattr(error, "code", "sync_failed"))


def _actionable_error(phase, error):
    code = _error_code(error)
    if code == "authentication_error":
        message = "API Key/Token توسط صرافی پذیرفته نشد؛ کلید را بررسی و دوباره Sync کنید."
    elif code == "unsafe_permissions":
        message = "مجوز برداشت کلید روشن است؛ کلید Read + Spot بدون Withdrawal بسازید."
    elif code in {"provider_connection_failed", "provider_http_429"}:
        message = "صرافی موقتاً پاسخ نداد؛ اتصال شبکه را بررسی و چند دقیقه بعد Sync کنید."
    elif phase == "fees":
        message = "کارمزد حساب از صرافی دریافت نشد؛ مجوز Read و دسترسی API را بررسی کنید."
    elif phase == "balances":
        message = "موجودی آزاد از صرافی دریافت نشد؛ مجوز Read و نوع کیف پول را بررسی کنید."
    elif phase == "markets":
        message = "بازارها و محدودیت سفارش از صرافی دریافت نشد؛ دوباره Sync کنید."
    elif phase == "permissions":
        message = "مجوزهای API قابل تأیید نیست؛ کلید Read + Spot بدون Withdrawal لازم است."
    elif phase == "credentials":
        message = "اطلاعات رمزنگاری‌شده اتصال قابل خواندن نیست؛ اتصال را حذف و دوباره بسازید."
    elif phase == "queue":
        message = "صف همگام‌سازی در دسترس نیست؛ وضعیت Worker maintenance را بررسی و Sync کنید."
    else:
        message = "همگام‌سازی کامل نشد؛ جزئیات اتصال را بررسی و دوباره Sync کنید."
    return f"sync.{phase}.{code}"[:80], message


def mark_sync_error(account_id, phase, error):
    code, message = _actionable_error(phase, error)
    UserExchangeAccount.objects.filter(pk=account_id).exclude(
        status=UserExchangeAccount.Status.DISABLED
    ).update(
        status=UserExchangeAccount.Status.ERROR,
        trading_enabled=False,
        last_error_code=code,
        last_error_message=message[:240],
        last_error_at=timezone.now(),
    )
    return {"code": code, "message": message}


def mark_sync_pending(account):
    if account.status == UserExchangeAccount.Status.DISABLED:
        raise ValidationError("اتصال حذف‌شده قابل همگام‌سازی نیست.")
    account.status = UserExchangeAccount.Status.PENDING
    account.trading_enabled = False
    account.save(update_fields=("status", "trading_enabled", "updated_at"))


def _fee_for_market(market, indexed_fees):
    quote = market.symbol.upper().split("/", 1)[-1]
    return (
        indexed_fees.get(market.symbol.upper())
        or indexed_fees.get(f"*/{quote}")
        or indexed_fees.get("*")
    )


def sync_exchange_account(account):
    current = UserExchangeAccount.objects.select_related("exchange").get(pk=account.pk)
    if current.status == UserExchangeAccount.Status.DISABLED:
        raise AdapterError("اتصال غیرفعال است.")

    phase = "credentials"
    try:
        adapter = get_adapter(
            current.exchange.adapter_code,
            credentials=_credentials_for(current),
            environment=current.environment,
        )
        phase = "permissions"
        permission = adapter.validate_credentials()
        phase = "markets"
        markets = adapter.fetch_markets()
        phase = "fees"
        fees = adapter.fetch_trading_fees()
        phase = "balances"
        balances = adapter.fetch_balance()
    except (AdapterError, ImproperlyConfigured, ValidationError) as error:
        mark_sync_error(current.pk, phase, error)
        raise
    except Exception as error:
        mark_sync_error(current.pk, phase, error)
        raise

    phase = "persist"
    try:
        with transaction.atomic():
            locked = (
                UserExchangeAccount.objects.select_for_update()
                .select_related("exchange")
                .get(pk=current.pk)
            )
            if locked.status == UserExchangeAccount.Status.DISABLED:
                raise AdapterError("اتصال هنگام Sync حذف شد.")

            now = timezone.now()
            locked.permissions = permission_payload(permission)
            locked.trading_enabled = permission.safe_for_trading
            locked.status = (
                UserExchangeAccount.Status.CONNECTED
                if permission.safe_for_trading
                else UserExchangeAccount.Status.RESTRICTED
            )
            locked.last_verified_at = now

            synced_market_keys = set()
            indexed_fees = {item.symbol.upper(): item for item in fees}
            for market in markets:
                if market.market_type not in {"spot", "margin"}:
                    continue
                base, _ = Asset.objects.get_or_create(symbol=market.base_asset.upper())
                quote, _ = Asset.objects.get_or_create(symbol=market.quote_asset.upper())
                metadata = dict(market.metadata)
                if market.market_type == "margin" and market.max_leverage == 1:
                    metadata.setdefault("leverage_status", "not_reported")
                fee = _fee_for_market(market, indexed_fees)
                row, _ = ExchangeMarket.objects.update_or_create(
                    exchange=locked.exchange,
                    symbol=market.symbol.upper(),
                    market_type=market.market_type,
                    defaults={
                        "base_asset": base,
                        "quote_asset": quote,
                        "min_amount": market.min_amount,
                        "max_amount": market.max_amount,
                        "amount_step": market.amount_step,
                        "price_step": market.price_step,
                        "min_notional": market.min_notional,
                        "max_leverage": market.max_leverage,
                        "maker_fee": fee.maker if fee else market.maker_fee,
                        "taker_fee": fee.taker if fee else market.taker_fee,
                        "active": market.active,
                        "metadata": {
                            **metadata,
                            "fee_source": "account_api" if fee else metadata.get("fee_source"),
                        },
                        "synced_at": now,
                    },
                )
                synced_market_keys.add((row.symbol, row.market_type))
            if synced_market_keys:
                for stale in locked.exchange.markets.filter(active=True).exclude(synced_at=now):
                    stale.active = False
                    stale.save(update_fields=("active",))

            for balance in balances:
                asset, _ = Asset.objects.get_or_create(symbol=balance.asset.upper())
                BalanceSnapshot.objects.create(
                    exchange_account=locked,
                    asset=asset,
                    wallet_scope="spot",
                    free_balance=balance.free,
                    locked_balance=balance.locked,
                    total_balance=balance.total,
                    captured_at=now,
                )
            locked.last_sync_at = now
            locked.last_error_code = ""
            locked.last_error_message = ""
            locked.last_error_at = None
            locked.save(
                update_fields=(
                    "permissions",
                    "trading_enabled",
                    "status",
                    "last_verified_at",
                    "last_sync_at",
                    "last_error_code",
                    "last_error_message",
                    "last_error_at",
                    "updated_at",
                )
            )
    except Exception as error:
        mark_sync_error(current.pk, phase, error)
        raise

    return {
        "account_id": current.pk,
        "status": locked.status,
        "market_count": len(synced_market_keys),
        "fee_count": len(fees),
        "balance_count": len(balances),
        "permissions": permission_payload(permission),
        "synced_at": now.isoformat(),
    }


def latest_balances(account):
    latest = {}
    queryset = account.balance_snapshots.select_related("asset").order_by("-captured_at", "asset")
    for snapshot in queryset:
        latest.setdefault(snapshot.asset_id, snapshot)
    return sorted(latest.values(), key=lambda item: item.asset.symbol)
