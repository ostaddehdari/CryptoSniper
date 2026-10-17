"""Owner-scoped, paginated Paper catalogue with common fill accounting."""

from django import forms
from django.core.paginator import Paginator

from apps.exchanges.models import UserExchangeAccount
from apps.portfolio.metrics import ACTIVE, summarize, trade_queryset

from .models import Trade


class TradeFilter(forms.Form):
    tab = forms.ChoiceField(
        choices=[("all", "همه"), ("open", "فعال"), ("history", "تاریخچه")], required=False
    )
    account = forms.ModelChoiceField(queryset=UserExchangeAccount.objects.none(), required=False)
    state = forms.ChoiceField(choices=[("", "همه وضعیت‌ها"), *Trade.State.choices], required=False)
    coin = forms.RegexField(regex=r"^[A-Za-z0-9/_-]{0,32}$", required=False, label="ارز یا نماد")
    source = forms.ChoiceField(
        choices=[("", "همه منابع"), ("manual", "ورود دستی"), ("smart_paste", "Smart Paste")],
        required=False,
    )

    def __init__(self, owner, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = UserExchangeAccount.objects.filter(owner=owner)
        self.fields["account"].label = "حساب / صرافی"
        self.fields["tab"].label = "نمایش"
        self.fields["state"].label = "وضعیت"
        self.fields["source"].label = "منبع"
        for field in self.fields.values():
            field.widget.attrs["class"] = "input"


def catalogue(owner, params):
    form = TradeFilter(owner, params)
    queryset = trade_queryset(owner).order_by("-created_at", "-pk")
    if not form.is_valid():
        queryset = queryset.none()
    else:
        data = form.cleaned_data
        if data.get("tab") == "open":
            queryset = queryset.filter(state__in=ACTIVE)
        elif data.get("tab") == "history":
            queryset = queryset.filter(state__in=["closed", "cancelled", "failed"])
        if data.get("account"):
            queryset = queryset.filter(account=data["account"])
        if data.get("state"):
            queryset = queryset.filter(state=data["state"])
        if data.get("coin"):
            queryset = queryset.filter(market__symbol__icontains=data["coin"].upper())
        if data.get("source") == "smart_paste":
            queryset = queryset.filter(signal__source__method="smart_paste")
        elif data.get("source") == "manual":
            from django.db.models import Q

            queryset = queryset.filter(Q(signal__source__method="manual") | Q(signal__isnull=True))
    page = Paginator(queryset, 20).get_page(params.get("page", 1))
    summary = summarize(owner, list(page.object_list))
    page.object_list = summary["trades"]
    query = params.copy()
    query.pop("page", None)
    return {
        "filter_form": form,
        "page": page,
        "trades": page.object_list,
        "filters_query": query.urlencode(),
        "nav": "paper",
    }


def trade_row(trade):
    stats = trade.stats
    return {
        "id": trade.pk,
        "symbol": trade.market.symbol,
        "account": trade.account.label,
        "exchange": trade.market.exchange.code,
        "state": trade.state,
        "mode": trade.mode,
        "market_type": trade.market.market_type,
        "side": trade.side,
        "entry": stats["average_entry"] or trade.entry_price,
        "current_price": stats["quote"]["price"] if stats["quote"] else None,
        "price_at": stats["quote"]["observed_at"] if stats["quote"] else None,
        "remaining": stats["remaining"],
        "realized": stats["realized"],
        "unrealized": stats["unrealized"],
        "quote_currency": stats["currency"],
        "duration_seconds": stats["duration_seconds"],
        "source": trade.signal.source.method if trade.signal else "manual",
    }
