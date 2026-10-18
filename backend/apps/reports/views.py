from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.security import session_api_required

from .exports import csv_bytes, svg_bytes
from .forms import ReportFilter
from .service import report_dataset


def _data(user, params):
    form = ReportFilter(user, params or None)
    if form.is_valid():
        return form, report_dataset(user, form.cleaned_data)
    return form, report_dataset(user, {"period": "day", "group": "total"})


@login_required
@never_cache
@require_GET
def center(request):
    form, dataset = _data(request.user, request.GET)
    query = request.GET.urlencode()
    return render(
        request,
        "reports/center.html",
        {"nav": "reports", "filter_form": form, "dataset": dataset, "export_query": query},
    )


@session_api_required
@never_cache
@require_GET
def api_report(request):
    form, dataset = _data(request.user, request.GET)
    return JsonResponse(
        {
            "errors": form.errors,
            "timezone": request.user.timezone,
            "period": dataset["period"],
            "group": dataset["group"],
            "total": dataset["total"],
            "rows": [
                {
                    "period_start": row.period_start,
                    "dimension": row.dimension_value,
                    "currency": row.currency,
                    "trades": row.trade_count,
                    "wins": row.wins,
                    "losses": row.losses,
                    "breakeven": row.breakeven,
                    "unknown": row.unknown_count,
                    "gross_realized": row.gross_realized,
                    "fees": row.fees,
                    "margin_interest": row.margin_interest,
                    "net_realized": row.net_realized,
                }
                for row in dataset["rows"]
            ],
        }
    )


@login_required
@never_cache
@require_GET
def export_csv(request):
    form, dataset = _data(request.user, request.GET)
    if not form.is_valid():
        return HttpResponse("invalid report filters", status=400)
    response = HttpResponse(csv_bytes(dataset), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cryptosniper-report.csv"'
    return response


@login_required
@never_cache
@require_GET
def export_chart(request):
    form, dataset = _data(request.user, request.GET)
    if not form.is_valid():
        return HttpResponse("invalid report filters", status=400)
    response = HttpResponse(svg_bytes(dataset), content_type="image/svg+xml; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cryptosniper-chart.svg"'
    return response
