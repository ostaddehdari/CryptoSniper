import hashlib

from django.db import transaction
from django.utils import timezone

from .adapters import AdapterError, get_adapter
from .models import Asset, BalanceSnapshot, ExchangeMarket, UserExchangeAccount
from .security import get_account_credentials


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


def sync_exchange_account(account):
    current = UserExchangeAccount.objects.select_related("exchange").get(pk=account.pk)
    if current.status == UserExchangeAccount.Status.DISABLED:
        raise AdapterError("اتصال غیرفعال است.")

    adapter = get_adapter(
        current.exchange.adapter_code,
        credentials=_credentials_for(current),
        environment=current.environment,
    )

    try:
        permission = adapter.validate_credentials()
        markets = adapter.fetch_markets()
        balances = adapter.fetch_balance()
    except AdapterError as error:
        # Persist the provider failure outside any surrounding success transaction.
        UserExchangeAccount.objects.filter(pk=current.pk).update(
            status=UserExchangeAccount.Status.ERROR,
            trading_enabled=False,
            last_error_code=getattr(error, "code", "adapter_error"),
            last_error_message=str(error)[:240],
            last_error_at=timezone.now(),
            updated_at=timezone.now(),
        )
        raise

    with transaction.atomic():
        locked = (
            UserExchangeAccount.objects.select_for_update()
            .select_related("exchange")
            .get(pk=current.pk)
        )
        now = timezone.now()
        locked.permissions = permission_payload(permission)
        locked.trading_enabled = permission.safe_for_trading
        locked.status = (
            UserExchangeAccount.Status.CONNECTED
            if permission.safe_for_trading
            else UserExchangeAccount.Status.RESTRICTED
        )
        locked.last_verified_at = now
        locked.last_error_code = ""
        locked.last_error_message = ""
        locked.last_error_at = None

        synced_market_keys = set()
        for market in markets:
            if market.market_type not in {"spot", "margin"}:
                continue
            base, _ = Asset.objects.get_or_create(symbol=market.base_asset.upper())
            quote, _ = Asset.objects.get_or_create(symbol=market.quote_asset.upper())
            metadata = dict(market.metadata)
            if market.market_type == "margin" and market.max_leverage == 1:
                metadata.setdefault("leverage_status", "not_reported")
            ExchangeMarket.objects.update_or_create(
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
                    "maker_fee": market.maker_fee,
                    "taker_fee": market.taker_fee,
                    "active": market.active,
                    "metadata": metadata,
                    "synced_at": now,
                },
            )
            synced_market_keys.add((market.symbol.upper(), market.market_type))

        if synced_market_keys:
            for stale in locked.exchange.markets.filter(active=True).exclude(synced_at=now):
                stale.active = False
                stale.save(update_fields=("active",))

        for balance in balances:
            asset, _ = Asset.objects.get_or_create(symbol=balance.asset.upper())
            BalanceSnapshot.objects.create(
                exchange_account=locked,
                asset=asset,
                free_balance=balance.free,
                locked_balance=balance.locked,
                total_balance=balance.total,
                captured_at=now,
            )

        locked.last_sync_at = now
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

    return {
        "account_id": current.pk,
        "status": locked.status,
        "market_count": len(synced_market_keys),
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
