"""Stage24 unified trade list, archive actions and real refresh.

The refresh endpoint performs a bounded, owner-scoped read sync. It never enables trading
and never submits orders.
"""

import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.security import session_api_required
from apps.exchanges.models import ExchangeMarket, LiveSpotOrder, UserExchangeAccount
from apps.exchanges.services import sync_exchange_account as run_account_sync
from apps.operations.external import observe_external_account
from apps.operations.models import ExternalObservation, ExternalTradePolicy
from apps.trading.models import Trade

from .external_utils import normalized_external


def _archived_filter(qs, view):
    if view == "archive":
        return qs.filter(archived_at__isnull=False)
    if view == "all":
        return qs
    return qs.filter(archived_at__isnull=True)


def _paper_row(trade):
    position = getattr(trade, "position", None)
    targets = list(trade.targets.order_by("position"))
    protection = getattr(trade, "protection", None)
    return {
        "key": f"paper:{trade.pk}",
        "kind": "paper",
        "id": trade.pk,
        "origin": "internal",
        "origin_label": "داخل CryptoSniper",
        "market_id": trade.market_id,
        "symbol": trade.market.symbol,
        "exchange": trade.account.exchange.code,
        "side": trade.side,
        "entry": str(trade.entry_price),
        "amount": str(trade.quantity),
        "position_amount": str(position.quantity) if position else "0",
        "state": trade.state,
        "open": trade.state
        in {
            Trade.State.QUEUED,
            Trade.State.SUBMITTING,
            Trade.State.PARTIAL,
            Trade.State.OPEN,
            Trade.State.UNCERTAIN,
        },
        "tp": [str(item.price) for item in targets],
        "stop_loss": str(protection.effective_stop) if protection else None,
        "created_at": trade.created_at.isoformat(),
        "updated_at": trade.updated_at.isoformat(),
        "archived_at": trade.archived_at.isoformat() if trade.archived_at else None,
        "chart": {"trade": trade.pk, "market": trade.market_id},
    }


def _live_row(order):
    return {
        "key": f"live:{order.pk}",
        "kind": "live",
        "id": order.pk,
        "origin": "internal_live",
        "origin_label": "سفارش Live داخل سایت",
        "market_id": order.market_id,
        "symbol": order.market.symbol,
        "exchange": order.account.exchange.code,
        "side": order.side,
        "entry": str(order.average_price or order.price or ""),
        "amount": str(order.amount),
        "position_amount": str(order.filled_amount),
        "state": order.state,
        "open": order.state
        in {
            LiveSpotOrder.State.PENDING,
            LiveSpotOrder.State.SUBMITTING,
            LiveSpotOrder.State.OPEN,
            LiveSpotOrder.State.PARTIAL,
            LiveSpotOrder.State.UNCERTAIN,
        },
        "tp": [],
        "stop_loss": None,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "archived_at": order.archived_at.isoformat() if order.archived_at else None,
        "chart": {"market": order.market_id},
    }


def _external_row(item):
    normalized = normalized_external(item)
    policy = ExternalTradePolicy.objects.filter(observation=item).first()
    market = None
    if normalized["symbol"]:
        market = (
            ExchangeMarket.objects.filter(
                exchange_id=item.account.exchange_id,
                symbol=normalized["symbol"],
                active=True,
            )
            .order_by("market_type")
            .first()
        )
    state = policy.state if policy else normalized["status"]
    open_state = state in {
        "new",
        "open",
        "active",
        "partial",
        "partially_filled",
        "uncertain",
    }
    tp = []
    stop = None
    if policy:
        tp = [str(value) for value in (policy.tp1, policy.tp2, policy.tp3) if value is not None]
        stop = str(policy.effective_stop)
    return {
        "key": f"external:{item.pk}",
        "kind": "external",
        "id": item.pk,
        "origin": "external",
        "origin_label": "خارج از CryptoSniper",
        "market_id": market.pk if market else None,
        "symbol": normalized["symbol"],
        "exchange": item.account.exchange.code,
        "side": normalized["side"],
        "entry": str(normalized["entry"] or ""),
        "amount": str(normalized["amount"] or ""),
        "position_amount": str(normalized["amount"] or ""),
        "state": state or "observed",
        "open": open_state,
        "tp": tp,
        "stop_loss": stop,
        "created_at": normalized["exact_time"].isoformat(),
        "updated_at": item.observed_at.isoformat(),
        "archived_at": item.archived_at.isoformat() if item.archived_at else None,
        "chart": {"external": item.pk, "market": market.pk if market else None},
    }


def _rows(user, view):
    paper = _archived_filter(
        Trade.objects.filter(owner=user)
        .select_related("account__exchange", "market")
        .prefetch_related("targets"),
        view,
    ).order_by("-updated_at")[:200]
    live = _archived_filter(
        LiveSpotOrder.objects.filter(owner=user).select_related("account__exchange", "market"),
        view,
    ).order_by("-updated_at")[:200]
    external = _archived_filter(
        ExternalObservation.objects.filter(
            account__owner=user,
            kind__in=("order", "fill", "history"),
        ).select_related("account__exchange"),
        view,
    ).order_by("-observed_at")[:200]
    rows = [_paper_row(row) for row in paper]
    rows += [_live_row(row) for row in live]
    rows += [_external_row(row) for row in external]
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows[:300]


@session_api_required
@never_cache
@require_GET
def api_trades(request):
    view = request.GET.get("view", "active")
    if view not in {"active", "archive", "all"}:
        return JsonResponse({"error": "invalid_view"}, status=400)
    rows = _rows(request.user, view)
    return JsonResponse(
        {
            "trades": rows,
            "view": view,
            "counts": {
                "visible": len(rows),
                "open": sum(1 for row in rows if row["open"]),
            },
            "as_of": timezone.now().isoformat(),
        }
    )


def _body(request):
    if request.content_type != "application/json" or len(request.body) > 4000:
        raise ValidationError("JSON معتبر لازم است.")
    try:
        value = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValidationError("JSON معتبر لازم است.") from error
    if not isinstance(value, dict):
        raise ValidationError("JSON باید شیء باشد.")
    return value


@session_api_required
@never_cache
@require_POST
def api_archive_trade(request):
    try:
        body = _body(request)
        kind = body.get("kind")
        pk = int(body.get("id"))
        archived = body.get("archived", True) is True
        value = timezone.now() if archived else None
        if kind == "paper":
            obj = Trade.objects.get(owner=request.user, pk=pk)
        elif kind == "live":
            obj = LiveSpotOrder.objects.get(owner=request.user, pk=pk)
        elif kind == "external":
            obj = ExternalObservation.objects.get(account__owner=request.user, pk=pk)
        else:
            raise ValidationError("نوع معامله نامعتبر است.")
        obj.archived_at = value
        obj.save(update_fields=("archived_at",))
        record_audit(
            "trade.archive_changed",
            request=request,
            user=request.user,
            metadata={"kind": kind, "id": pk, "archived": archived},
        )
        return JsonResponse(
            {
                "ok": True,
                "kind": kind,
                "id": pk,
                "archived_at": value.isoformat() if value else None,
            }
        )
    except (
        ValueError,
        TypeError,
        ValidationError,
        Trade.DoesNotExist,
        LiveSpotOrder.DoesNotExist,
        ExternalObservation.DoesNotExist,
    ) as error:
        return JsonResponse({"error": str(error)}, status=400)


@session_api_required
@never_cache
@require_POST
def api_refresh_trades(request):
    """Read-sync all usable accounts now so the refresh button has an observable result."""
    accounts = list(
        UserExchangeAccount.objects.for_user(request.user)
        .filter(status__in=("connected", "restricted"))
        .exclude(credentials_encrypted="")
        .select_related("exchange")[:8]
    )
    results = []
    for account in accounts:
        state = {"account_id": account.pk, "exchange": account.exchange.code}
        try:
            synced = run_account_sync(account)
            state["sync"] = "ok"
            state["market_count"] = synced.get("market_count", 0)
            state["balance_count"] = synced.get("balance_count", 0)
        except (
            Exception
        ) as error:  # provider failures are returned per account, never leaked with credentials
            state["sync"] = "error"
            state["sync_error"] = type(error).__name__
        try:
            state["observation"] = observe_external_account(account)
        except Exception as error:
            state["observation"] = "error"
            state["observation_error"] = type(error).__name__
        results.append(state)
    record_audit(
        "trade.refresh_requested",
        request=request,
        user=request.user,
        metadata={"accounts": len(accounts)},
    )
    rows = _rows(request.user, "active")
    return JsonResponse(
        {
            "ok": True,
            "accounts": results,
            "trades": rows,
            "open": sum(1 for row in rows if row["open"]),
            "as_of": timezone.now().isoformat(),
        }
    )
