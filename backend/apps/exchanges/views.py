from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.audit import record_audit
from apps.accounts.security import session_api_required, step_up_required

from .forms import ExchangeConnectionForm, LiveSpotOrderForm
from .live_orders import queue_live_spot_order
from .models import Exchange, LiveSpotOrder, UserExchangeAccount
from .security import revoke_account_credentials, rotate_account_credentials
from .services import latest_balances
from .tasks import live_spot_order, sync_exchange_account


def _owned_account(user, pk):
    return get_object_or_404(
        UserExchangeAccount.objects.for_user(user).select_related("exchange"), pk=pk
    )


@login_required
@never_cache
@require_GET
def exchange_center(request):
    accounts = UserExchangeAccount.objects.for_user(request.user).select_related("exchange")
    catalog = Exchange.objects.filter(enabled=True)
    return render(
        request,
        "exchanges/center.html",
        {"accounts": accounts, "catalog": catalog, "nav": "exchanges"},
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def add_exchange_account(request):
    form = ExchangeConnectionForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save()
        record_audit(
            "exchange_account.added",
            request=request,
            user=request.user,
            metadata={
                "exchange": account.exchange.code,
                "environment": account.environment,
                "account_id": account.pk,
            },
        )
        sync_exchange_account.apply_async(args=[account.pk], queue="maintenance")
        messages.success(request, "اتصال ساخته شد و بررسی امن آن در صف قرار گرفت.")
        return redirect("exchange-account-detail", pk=account.pk)
    return render(
        request,
        "exchanges/add.html",
        {"form": form, "nav": "exchanges"},
    )


@login_required
@never_cache
@require_GET
def exchange_account_detail(request, pk):
    account = _owned_account(request.user, pk)
    markets = account.exchange.markets.filter(active=True)[:50]
    return render(
        request,
        "exchanges/detail.html",
        {
            "account": account,
            "balances": latest_balances(account),
            "markets": markets,
            "live_enabled": settings.LIVE_TRADING_ENABLED,
            "live_order_form": LiveSpotOrderForm(request.user, account),
            "live_orders": LiveSpotOrder.objects.filter(owner=request.user, account=account)[:20],
            "nav": "exchanges",
        },
    )


@login_required
@require_POST
@step_up_required
def submit_live_spot_order(request, pk):
    account = _owned_account(request.user, pk)
    form = LiveSpotOrderForm(request.user, account, request.POST)
    try:
        if not form.is_valid():
            errors = [str(item) for values in form.errors.values() for item in values]
            raise ValidationError("؛ ".join(errors))
        order, created = queue_live_spot_order(request.user, account, form.cleaned_data)
        if created:
            record_audit(
                "live_spot_order.queued",
                request=request,
                user=request.user,
                metadata={
                    "order_id": order.pk,
                    "exchange": account.exchange.code,
                    "market_id": order.market_id,
                    "side": order.side,
                },
            )
            live_spot_order.apply_async(args=[order.pk], queue="orders")
            messages.success(request, "سفارش واقعی با شناسه یکتا در صف امن orders ثبت شد.")
        else:
            messages.info(request, "این درخواست قبلاً ثبت شده و دوباره ارسال نشد.")
    except (ValidationError, IntegrityError, ValueError) as error:
        messages.error(request, str(error))
    return redirect("exchange-account-detail", pk=account.pk)


@login_required
@require_POST
def request_account_sync(request, pk):
    account = _owned_account(request.user, pk)
    if account.status == UserExchangeAccount.Status.DISABLED:
        messages.error(request, "اتصال غیرفعال است و همگام‌سازی نمی‌شود.")
    else:
        sync_exchange_account.apply_async(args=[account.pk], queue="maintenance")
        record_audit(
            "exchange_account.sync_requested",
            request=request,
            user=request.user,
            metadata={"exchange": account.exchange.code, "account_id": account.pk},
        )
        messages.success(request, "بررسی مجوز، بازارها و موجودی در صف قرار گرفت.")
    return redirect("exchange-account-detail", pk=account.pk)


@login_required
@require_POST
def disable_exchange_account(request, pk):
    account = _owned_account(request.user, pk)
    account.status = UserExchangeAccount.Status.DISABLED
    account.trading_enabled = False
    account.save(update_fields=("status", "trading_enabled", "updated_at"))
    record_audit(
        "exchange_account.disabled",
        request=request,
        user=request.user,
        metadata={"exchange": account.exchange.code, "account_id": account.pk},
    )
    messages.success(request, "اتصال فوراً غیرفعال شد.")
    return redirect("exchange-account-detail", pk=account.pk)


@login_required
@require_POST
@step_up_required
def rotate_exchange_account(request, pk):
    account = _owned_account(request.user, pk)
    if account.status == UserExchangeAccount.Status.DISABLED or not account.credentials_encrypted:
        messages.error(request, "اتصال غیرفعال یا فاقد کلید قابل گردش است.")
    else:
        version = rotate_account_credentials(account)
        account.trading_enabled = False
        account.status = UserExchangeAccount.Status.PENDING
        account.save(update_fields=("trading_enabled", "status", "updated_at"))
        record_audit(
            "exchange_account.credentials_rotated",
            request=request,
            user=request.user,
            metadata={"account_id": account.pk, "key_version": version},
        )
        messages.success(request, "کلید رمزنگاری گردش یافت؛ اتصال تا بررسی مجدد غیرفعال است.")
    return redirect("exchange-account-detail", pk=account.pk)


@login_required
@require_POST
@step_up_required
def revoke_exchange_account(request, pk):
    account = _owned_account(request.user, pk)
    revoke_account_credentials(account)
    record_audit(
        "exchange_account.credentials_revoked",
        request=request,
        user=request.user,
        metadata={"account_id": account.pk, "exchange": account.exchange.code},
    )
    messages.success(request, "کلید اتصال حذف و اجرای آن فوراً متوقف شد.")
    return redirect("exchange-account-detail", pk=account.pk)


def _account_payload(account):
    return {
        "id": account.pk,
        "exchange": account.exchange.code,
        "label": account.label,
        "environment": account.environment,
        "status": account.status,
        "credential_hint": account.credential_hint,
        "trading_permission_verified": account.trading_enabled,
        "permissions": account.permissions,
        "last_verified_at": account.last_verified_at,
        "last_sync_at": account.last_sync_at,
    }


@session_api_required
@never_cache
@require_GET
def api_exchanges(request):
    catalog = [
        {
            "code": exchange.code,
            "name": exchange.name,
            "spot": exchange.spot_supported,
            "margin": exchange.margin_supported,
            "futures": False,
            "sandbox": exchange.sandbox_supported,
        }
        for exchange in Exchange.objects.filter(enabled=True)
    ]
    accounts = [
        _account_payload(account)
        for account in UserExchangeAccount.objects.for_user(request.user).select_related("exchange")
    ]
    response = JsonResponse({"exchanges": catalog, "accounts": accounts})
    response["Cache-Control"] = "no-store"
    return response


@session_api_required
@never_cache
@require_GET
def api_exchange_account(request, pk):
    account = _owned_account(request.user, pk)
    response = JsonResponse({"account": _account_payload(account)})
    response["Cache-Control"] = "no-store"
    return response
