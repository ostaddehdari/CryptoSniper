"""Read-only Stage23 acceptance and Bitunix diagnostics.

This command never places, edits or cancels an exchange order and never prints API secrets.
"""

import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts.models import WalletConnection
from apps.alerts.models import Notification, PriceAlert
from apps.core.health import dependency_status
from apps.exchanges.adapters import AdapterError, get_adapter
from apps.exchanges.models import BalanceSnapshot, ExchangeMarket, LiveSpotOrder, UserExchangeAccount
from apps.exchanges.security import get_account_credentials
from apps.marketdata.models import FavoriteAsset, Watchlist
from apps.operations.models import AccountControl, ExternalObservation, RecoveryIssue, WorkerHeartbeat
from apps.reports.models import ReportRefreshState
from apps.signals.models import Signal, SignalSource, TelegramAccount, TelegramChannel, TelegramMessage
from apps.tradeplans.models import TradePlan


class Command(BaseCommand):
    help = (
        "Read-only acceptance matrix for Stage23 and deep Bitunix diagnostics. "
        "No real order is submitted."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", default="")
        parser.add_argument("--account-id", type=int)
        parser.add_argument("--skip-network", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        rows = []

        def add(section, name, status, detail="", action=""):
            rows.append(
                {
                    "section": section,
                    "name": name,
                    "status": status,
                    "detail": str(detail),
                    "action": str(action),
                }
            )

        # Infrastructure
        try:
            deps = dependency_status()
            for key, ok in deps.items():
                add("infra", key, "PASS" if ok else "FAIL", ok)
        except Exception as exc:
            add("infra", "dependencies", "FAIL", type(exc).__name__)

        cutoff = timezone.now() - timedelta(seconds=95)
        heartbeats = {h.queue: h for h in WorkerHeartbeat.objects.all()}
        for queue in settings.OPERATION_QUEUES:
            hb = heartbeats.get(queue)
            fresh = bool(hb and hb.seen_at >= cutoff)
            detail = (
                f"seen_at={hb.seen_at.isoformat()} lag={hb.lag_seconds}s"
                if hb
                else "no heartbeat row"
            )
            add(
                "workers",
                queue,
                "PASS" if fresh else "FAIL",
                detail,
                "سرویس Worker مربوط به این صف را بررسی/Restart کنید." if not fresh else "",
            )

        # UI/routes
        required_routes = (
            "react-app",
            "api-ui-bootstrap",
            "api-wallets",
            "api-exchange-create",
            "api-exchange-diagnostics",
            "api-fix-loss",
            "api-live-orders",
            "api-telegram-state",
            "api-operations-health",
        )
        for name in required_routes:
            try:
                add("web", name, "PASS", reverse(name, args=[1]) if name == "api-exchange-diagnostics" else reverse(name))
            except NoReverseMatch as exc:
                add("web", name, "FAIL", str(exc))

        static_root = Path(settings.BASE_DIR) / "static" / "react"
        for filename in ("app.js", "app.css"):
            target = static_root / filename
            add("react", filename, "PASS" if target.is_file() else "FAIL", target)

        # Feature/model smoke checks.
        model_checks = (
            ("wallets", "WalletConnection", WalletConnection),
            ("watchlist", "Watchlist", Watchlist),
            ("favorites", "FavoriteAsset", FavoriteAsset),
            ("signals", "SignalSource", SignalSource),
            ("signals", "Signal", Signal),
            ("telegram", "TelegramAccount", TelegramAccount),
            ("telegram", "TelegramChannel", TelegramChannel),
            ("telegram", "TelegramMessage", TelegramMessage),
            ("alerts", "PriceAlert", PriceAlert),
            ("alerts", "Notification", Notification),
            ("reports", "ReportRefreshState", ReportRefreshState),
            ("tradeplans", "TradePlan", TradePlan),
            ("live_orders", "LiveSpotOrder", LiveSpotOrder),
        )
        for section, name, model in model_checks:
            try:
                add(section, name, "PASS", f"rows={model.objects.count()}")
            except Exception as exc:
                add(section, name, "FAIL", type(exc).__name__)

        add(
            "live-trading",
            "LIVE_TRADING_ENABLED",
            "PASS" if settings.LIVE_TRADING_ENABLED else "FAIL",
            settings.LIVE_TRADING_ENABLED,
            (
                "برای ارسال سفارش واقعی باید LIVE_TRADING_ENABLED=true در env سرور باشد؛ "
                "بعد از رفع همه خطاهای اتصال و تأیید مجوزها فعال شود."
                if not settings.LIVE_TRADING_ENABLED
                else ""
            ),
        )

        # Account selection.
        accounts = (
            UserExchangeAccount.objects.select_related("owner", "exchange")
            .filter(environment="live", exchange__adapter_code="bitunix")
            .order_by("pk")
        )
        if options["username"]:
            accounts = accounts.filter(owner__username=options["username"])
        if options["account_id"]:
            accounts = accounts.filter(pk=options["account_id"])

        if not accounts.exists():
            add(
                "bitunix",
                "account",
                "FAIL",
                "No live Bitunix account found.",
                "ابتدا اتصال Bitunix را در CryptoSniper ذخیره کنید.",
            )

        for account in accounts:
            prefix = f"account:{account.pk}:{account.label}"
            add("bitunix", prefix + ":environment", "PASS" if account.environment == "live" else "FAIL", account.environment)
            add("bitunix", prefix + ":status", "PASS" if account.status == "connected" else "FAIL", account.status, account.last_error_message)
            add("bitunix", prefix + ":trading_enabled", "PASS" if account.trading_enabled else "FAIL", account.trading_enabled)
            if account.last_error_code:
                add("bitunix", prefix + ":last_error", "FAIL", f"{account.last_error_code}: {account.last_error_message}")

            try:
                credentials = get_account_credentials(account)
                add("bitunix", prefix + ":credentials_decrypt", "PASS", f"api_key_present={bool(credentials.get('api_key'))}; secret_present={bool(credentials.get('api_secret'))}")
            except Exception as exc:
                add("bitunix", prefix + ":credentials_decrypt", "FAIL", type(exc).__name__)
                continue

            no_withdraw = credentials.get("no_withdrawal_confirmed") == "true"
            ip_confirmed = credentials.get("ip_restricted_confirmed") == "true"
            add(
                "bitunix",
                prefix + ":withdraw_disabled_confirmed",
                "PASS" if no_withdraw else "FAIL",
                no_withdraw,
                "در API Bitunix مجوز Withdrawal را خاموش کنید و تأیید آن را در اتصال ثبت کنید." if not no_withdraw else "",
            )
            add(
                "bitunix",
                prefix + ":ip_whitelist_confirmed",
                "PASS" if ip_confirmed else "WARN",
                ip_confirmed,
                "برای کلید API، IP ثابت سرور را در whitelist محدود کنید." if not ip_confirmed else "",
            )

            permissions = account.permissions or {}
            add("bitunix", prefix + ":can_read", "PASS" if permissions.get("can_read") is True else "FAIL", permissions.get("can_read"))
            add("bitunix", prefix + ":can_trade_spot", "PASS" if permissions.get("can_trade_spot") is True else "FAIL", permissions.get("can_trade_spot"))
            add("bitunix", prefix + ":can_withdraw_false", "PASS" if permissions.get("can_withdraw") is False else "FAIL", permissions.get("can_withdraw"))

            control, _ = AccountControl.objects.get_or_create(account=account)
            add(
                "bitunix",
                prefix + ":operations_paused",
                "PASS" if not control.paused else "FAIL",
                control.paused,
                control.reason,
            )
            unresolved = RecoveryIssue.objects.filter(account=account, resolved=False).count()
            add("bitunix", prefix + ":recovery_issues", "PASS" if unresolved == 0 else "WARN", unresolved)

            market_count = ExchangeMarket.objects.filter(
                exchange=account.exchange, market_type="spot", active=True
            ).count()
            usdt_market_count = ExchangeMarket.objects.filter(
                exchange=account.exchange,
                market_type="spot",
                active=True,
                quote_asset__symbol="USDT",
            ).count()
            add("bitunix", prefix + ":markets_db", "PASS" if market_count else "FAIL", f"spot={market_count} usdt={usdt_market_count}")

            snapshots = BalanceSnapshot.objects.filter(exchange_account=account)
            add("bitunix", prefix + ":balance_snapshots", "PASS" if snapshots.exists() else "WARN", f"rows={snapshots.count()}")

            blockers = []
            if not settings.LIVE_TRADING_ENABLED:
                blockers.append("LIVE_TRADING_ENABLED=false")
            if account.environment != "live":
                blockers.append("account environment is not live")
            if account.status != "connected":
                blockers.append(f"account status={account.status}")
            if not account.trading_enabled:
                blockers.append("account.trading_enabled=false")
            if permissions.get("can_withdraw") is not False:
                blockers.append("can_withdraw is not explicitly false")
            if permissions.get("can_trade_spot") is not True:
                blockers.append("can_trade_spot is not true")
            if control.paused:
                blockers.append("operations account is paused")
            if usdt_market_count == 0:
                blockers.append("no active USDT spot markets")
            orders_hb = heartbeats.get("orders")
            if not orders_hb or orders_hb.seen_at < cutoff:
                blockers.append("orders worker heartbeat is stale")
            add(
                "live-trading",
                prefix + ":preflight",
                "PASS" if not blockers else "FAIL",
                "ready" if not blockers else "; ".join(blockers),
                "این تست فقط gateها را بررسی می‌کند و هیچ سفارش واقعی ارسال نمی‌کند.",
            )

            if options["skip_network"]:
                add("bitunix-network", prefix, "WARN", "network probes skipped")
                continue

            adapter = get_adapter(
                "bitunix",
                credentials=credentials,
                environment="live",
            )
            try:
                markets = adapter.fetch_markets()
                add("bitunix-network", prefix + ":public_markets", "PASS", f"markets={len(markets)}")
            except AdapterError as exc:
                add("bitunix-network", prefix + ":public_markets", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}")
                markets = []

            try:
                permission = adapter.validate_credentials()
                add(
                    "bitunix-network",
                    prefix + ":private_auth",
                    "PASS",
                    f"read={permission.can_read} trade_spot={permission.can_trade_spot}",
                )
            except AdapterError as exc:
                add(
                    "bitunix-network",
                    prefix + ":private_auth",
                    "FAIL",
                    f"{getattr(exc, 'code', 'adapter_error')}: {exc}",
                    "کد دقیق Bitunix را بخوانید؛ 10004=IP whitelist، 10007=signature/secret، 10011=clock.",
                )

            try:
                balances = adapter.fetch_balance()
                nonzero = [b for b in balances if b.total > 0]
                add("bitunix-network", prefix + ":private_balance", "PASS", f"assets={len(balances)} nonzero={len(nonzero)}")
            except AdapterError as exc:
                add("bitunix-network", prefix + ":private_balance", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}")

            try:
                info = adapter._request("GET", "/api/spot/v1/user/info", signed=True)
                uid_present = isinstance(info, dict) and bool(info.get("uid"))
                add("bitunix-network", prefix + ":user_info", "PASS" if uid_present else "WARN", f"uid_present={uid_present}")
            except AdapterError as exc:
                add("bitunix-network", prefix + ":user_info", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}")

            symbol = "BTC/USDT"
            if not any(m.symbol == symbol for m in markets):
                symbol = next((m.symbol for m in markets if m.quote_asset == "USDT"), "")
            if symbol:
                try:
                    ticker = adapter.fetch_ticker(symbol)
                    add("bitunix-network", prefix + ":ticker", "PASS", f"{symbol} price={ticker.price}")
                except AdapterError as exc:
                    add("bitunix-network", prefix + ":ticker", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}")
                try:
                    provider_symbol = symbol.replace("/", "")
                    pending = adapter._request(
                        "POST",
                        "/api/spot/v1/order/pending/list",
                        {"symbol": provider_symbol},
                        signed=True,
                    )
                    count = len(pending) if isinstance(pending, list) else len(pending.get("data", [])) if isinstance(pending, dict) else 0
                    add("bitunix-network", prefix + ":open_orders_read", "PASS", f"symbol={symbol} rows={count}")
                except AdapterError as exc:
                    add("bitunix-network", prefix + ":open_orders_read", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}")

            external_count = ExternalObservation.objects.filter(account=account).count()
            add("external-trades", prefix, "PASS" if external_count else "WARN", f"observations={external_count}")

        summary = {
            "pass": sum(r["status"] == "PASS" for r in rows),
            "warn": sum(r["status"] == "WARN" for r in rows),
            "fail": sum(r["status"] == "FAIL" for r in rows),
            "total": len(rows),
            "live_order_was_submitted": False,
        }

        if options["as_json"]:
            self.stdout.write(json.dumps({"summary": summary, "checks": rows}, ensure_ascii=False, indent=2, default=str))
            return

        current = None
        for row in rows:
            if row["section"] != current:
                current = row["section"]
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {current} =="))
            marker = {"PASS": "✓", "WARN": "!", "FAIL": "✗"}[row["status"]]
            line = f"{marker} {row['status']:<4} {row['name']}: {row['detail']}"
            if row["status"] == "FAIL":
                self.stdout.write(self.style.ERROR(line))
            elif row["status"] == "WARN":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(self.style.SUCCESS(line))
            if row["action"]:
                self.stdout.write(f"    ACTION: {row['action']}")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nSUMMARY: PASS={summary['pass']} WARN={summary['warn']} FAIL={summary['fail']} TOTAL={summary['total']}"
            )
        )
        self.stdout.write("Safety: this diagnostic did NOT place, edit, or cancel any real order.")
