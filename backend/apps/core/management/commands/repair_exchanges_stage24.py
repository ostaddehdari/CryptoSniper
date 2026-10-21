"""Stage24 exchange repair and price-integrity diagnostics.

Uses already encrypted credentials stored by CryptoSniper. It never prints secrets and never
places/cancels/edits an order. With --apply it re-validates and re-syncs account state.
"""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.exchanges.adapters import AdapterError, UnsafePermissionError, get_adapter
from apps.exchanges.models import ExchangeMarket, UserExchangeAccount
from apps.exchanges.security import get_account_credentials
from apps.exchanges.services import sync_exchange_account
from apps.marketdata.feeds import get_quote, refresh_quote
from apps.operations.recovery import reconcile_account


def _action(exchange_code, detail, permission=None):
    text = str(detail).lower()
    if isinstance(permission, dict):
        if permission.get("can_withdraw") is True:
            return "مجوز Withdrawal را در خود صرافی خاموش کنید؛ CryptoSniper کلید دارای برداشت را نمی‌پذیرد."
        if permission.get("can_read") is not True:
            return "مجوز Read را برای API فعال کنید."
        if permission.get("can_trade_spot") is not True:
            return "مجوز Spot Trading را برای API فعال کنید."
    if "401" in text or "403" in text or "authentication" in text:
        return "API Key/Secret/Token/Passphrase و مجوزهای API را در خود صرافی بررسی کنید."
    if "whitelist" in text or "10004" in text or "ip" in text and "restrict" in text:
        return "IP ثابت سرور 5.61.27.185 را در IP whitelist کلید API قرار دهید."
    if "10007" in text or "signature" in text:
        return "Secret/Passphrase و نوع امضای API را بررسی کنید؛ کلید را دوباره ذخیره کنید."
    if "10011" in text or "timestamp" in text or "clock" in text:
        return "همگام‌سازی ساعت/NTP سرور را بررسی کنید."
    if "404" in text:
        return f"Endpoint فعلی Adapter {exchange_code} با API این حساب/نسخه سازگار نیست؛ گزارش برای اصلاح Adapter لازم است."
    if "complete api" in text or "اطلاعات کامل" in text:
        return "اطلاعات لازم API ناقص است؛ برای WEEX علاوه بر Key/Secret، Passphrase هم لازم است."
    return "جزئیات Provider را در همین گزارش بررسی کنید؛ Secret در گزارش چاپ نمی‌شود."


class Command(BaseCommand):
    help = "Repair all saved live exchange connections and verify direct/display prices without trading."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--include-disabled", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        rows = []

        def add(account, check, status, detail="", action=""):
            rows.append(
                {
                    "account_id": account.pk if account else None,
                    "exchange": account.exchange.code if account else "",
                    "label": account.label if account else "",
                    "check": check,
                    "status": status,
                    "detail": str(detail),
                    "action": str(action),
                }
            )

        qs = (
            UserExchangeAccount.objects.select_related("owner", "exchange")
            .filter(environment="live")
            .exclude(exchange__adapter_code="simulator")
            .exclude(exchange__code="binance")
            .order_by("exchange__code", "pk")
        )
        if options["username"]:
            qs = qs.filter(owner__username=options["username"])
        if not options["include_disabled"]:
            qs = qs.exclude(status=UserExchangeAccount.Status.DISABLED)

        accounts = list(qs)
        if not accounts:
            self.stdout.write(self.style.WARNING("No live exchange accounts found."))
            return

        for account in accounts:
            add(account, "stored_state", "INFO", f"status={account.status} trading={account.trading_enabled} hint={account.credential_hint}")
            if account.status == UserExchangeAccount.Status.DISABLED:
                add(account, "disabled", "SKIP", "اتصال عمداً غیرفعال است.", "برای فعال‌سازی مجدد باید کاربر صریحاً اتصال جدید/فعال بسازد.")
                continue

            try:
                credentials = get_account_credentials(account)
                required = ["api_key"]
                if account.exchange.adapter_code != "nobitex":
                    required.append("api_secret")
                if account.exchange.adapter_code == "weex":
                    required.append("passphrase")
                missing = [key for key in required if not credentials.get(key)]
                if missing:
                    add(account, "credentials", "FAIL", "missing=" + ",".join(missing), _action(account.exchange.code, "complete api"))
                    continue
                add(account, "credentials", "PASS", "encrypted credentials decrypted; secrets hidden")
            except Exception as exc:
                add(account, "credentials", "FAIL", type(exc).__name__, "کلید رمزنگاری یا رکورد اتصال را بررسی کنید.")
                continue

            adapter = get_adapter(
                account.exchange.adapter_code,
                credentials=credentials,
                environment=account.environment,
            )

            markets = []
            sample = None
            try:
                markets = adapter.fetch_markets()
                sample = next((m for m in markets if m.symbol == "BTC/USDT" and m.active), None)
                sample = sample or next((m for m in markets if m.quote_asset == "USDT" and m.active), None)
                add(account, "public_markets", "PASS", f"markets={len(markets)} sample={getattr(sample, 'symbol', None)}")
            except AdapterError as exc:
                add(
                    account,
                    "public_markets",
                    "FAIL",
                    f"{getattr(exc, 'code', 'adapter_error')}: {exc}",
                    _action(account.exchange.code, exc),
                )

            if sample:
                try:
                    ticker = adapter.fetch_ticker(sample.symbol)
                    book = adapter.fetch_orderbook(sample.symbol)
                    bid = book.get("bids", [[None]])[0][0] if book.get("bids") else None
                    ask = book.get("asks", [[None]])[0][0] if book.get("asks") else None
                    consistent = not (bid and ask) or bid <= ticker.price <= ask or abs(ticker.price - ((bid + ask) / 2)) / ticker.price < 0.01
                    add(
                        account,
                        "direct_price",
                        "PASS" if consistent else "WARN",
                        f"{sample.symbol} price={ticker.price} bid={bid} ask={ask} observed_at={ticker.observed_at.isoformat()}",
                        "" if consistent else "قیمت مستقیم و Order Book بیش از حد اختلاف دارند؛ داده این صرافی را نمایش ندهید تا بررسی شود.",
                    )
                except (AdapterError, ValueError, TypeError) as exc:
                    add(account, "direct_price", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}", _action(account.exchange.code, exc))

            permission = None
            try:
                report = adapter.validate_credentials()
                permission = {
                    "can_read": report.can_read,
                    "can_trade_spot": report.can_trade_spot,
                    "can_withdraw": report.can_withdraw,
                    "ip_restricted": report.ip_restricted,
                }
                safe = report.safe_for_trading
                add(
                    account,
                    "permissions",
                    "PASS" if safe else "WARN",
                    json.dumps(permission, ensure_ascii=False),
                    "" if safe else _action(account.exchange.code, "permissions", permission),
                )
            except UnsafePermissionError as exc:
                add(account, "permissions", "FAIL", str(exc), "Withdrawal را روی این API Key خاموش و سپس دوباره Sync کنید.")
            except AdapterError as exc:
                add(account, "private_auth", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}", _action(account.exchange.code, exc))

            try:
                balances = adapter.fetch_balance()
                nonzero = [b for b in balances if b.total > 0]
                add(account, "private_balance", "PASS", f"assets={len(balances)} nonzero={len(nonzero)}")
            except AdapterError as exc:
                add(account, "private_balance", "FAIL", f"{getattr(exc, 'code', 'adapter_error')}: {exc}", _action(account.exchange.code, exc))

            if options["apply"]:
                try:
                    result = sync_exchange_account(account)
                    account.refresh_from_db()
                    add(
                        account,
                        "sync_apply",
                        "PASS" if account.status == "connected" else "WARN",
                        f"status={account.status} trading={account.trading_enabled} markets={result['market_count']} balances={result['balance_count']}",
                        "" if account.status == "connected" else _action(account.exchange.code, "permissions", account.permissions),
                    )
                except AdapterError as exc:
                    account.refresh_from_db()
                    add(account, "sync_apply", "FAIL", f"status={account.status}; {getattr(exc, 'code', 'adapter_error')}: {exc}", _action(account.exchange.code, exc))

                if account.status in {"connected", "restricted"} and account.permissions.get("can_read") is True and account.permissions.get("can_withdraw") is False:
                    try:
                        observed = reconcile_account(account.pk)
                        add(account, "external_read_sync", "PASS", observed)
                    except Exception as exc:
                        add(account, "external_read_sync", "WARN", type(exc).__name__, "خواندن External Orders/History برای این Adapter کامل نیست یا Provider آن را نپذیرفت.")

            # Verify the exact quote path used by UI for one highly liquid market.
            db_market = (
                ExchangeMarket.objects.filter(
                    exchange=account.exchange,
                    market_type="spot",
                    active=True,
                    symbol="BTC/USDT",
                )
                .select_related("exchange")
                .first()
            )
            if db_market:
                outcome = refresh_quote(db_market)
                quote = get_quote(db_market)
                if outcome.get("status") == "ok" and quote and not quote.get("stale"):
                    add(
                        account,
                        "display_price",
                        "PASS",
                        f"source={quote.get('source')} price={quote.get('price')} age={quote.get('age_seconds')}s observed_at={quote.get('observed_at')}",
                    )
                else:
                    add(account, "display_price", "FAIL", f"refresh={outcome.get('status')} quote={bool(quote)}", "قیمت این بازار در UI نباید به‌عنوان قیمت زنده نمایش داده شود تا Feed اصلاح شود.")

        failures = sum(r["status"] == "FAIL" for r in rows)
        warnings = sum(r["status"] == "WARN" for r in rows)
        connected = UserExchangeAccount.objects.filter(pk__in=[a.pk for a in accounts], status="connected").count()
        summary = {
            "accounts": len(accounts),
            "connected_after": connected,
            "fail": failures,
            "warn": warnings,
            "apply": bool(options["apply"]),
            "generated_at": timezone.now().isoformat(),
            "safety": "No order was placed, edited, or cancelled.",
        }

        if options["as_json"]:
            self.stdout.write(json.dumps({"summary": summary, "checks": rows}, ensure_ascii=False, indent=2, default=str))
            return

        current = None
        for row in rows:
            identity = (row["account_id"], row["exchange"], row["label"])
            if identity != current:
                current = identity
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n== #{row['account_id']} {row['exchange']} · {row['label']} =="))
            marker = {"PASS": "✓", "WARN": "!", "FAIL": "✗", "INFO": "i", "SKIP": "-"}.get(row["status"], "?")
            line = f"{marker} {row['status']:<4} {row['check']}: {row['detail']}"
            if row["status"] == "FAIL":
                self.stdout.write(self.style.ERROR(line))
            elif row["status"] == "WARN":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)
            if row["action"]:
                self.stdout.write(f"    ACTION: {row['action']}")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nSUMMARY accounts={summary['accounts']} connected_after={summary['connected_after']} FAIL={failures} WARN={warnings}"
            )
        )
        self.stdout.write("Safety: no real order was submitted by this command.")
