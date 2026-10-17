from apps.accounts import views as account_views
from apps.alerts import notifications as notification_views
from apps.alerts import views as alert_views
from apps.core import views
from apps.core.health import dependency_status
from apps.exchanges import views as exchange_views
from apps.marketdata import views as market_views
from apps.marketdata import watchlists as watchlist_views
from apps.operations import views as operation_views
from apps.portfolio import external_views
from apps.portfolio import views as portfolio_views
from apps.signals import views as inbox_views
from apps.tradeplans import context as trade_context
from apps.tradeplans import views as plan_views
from apps.trading import risk as paper_risk_views
from apps.trading import views as paper_views
from django.http import JsonResponse
from django.urls import path


def live(request):
    return JsonResponse({"status": "ok", "service": "cryptosniper", "stage": "S12"})


def ready(request):
    checks = dependency_status()
    healthy = all(checks.values())
    response = JsonResponse(
        {"status": "ready" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )
    response["Cache-Control"] = "no-store"
    return response


urlpatterns = [
    path("external/<int:pk>/", external_views.detail, name="external-detail"),
    path("dashboard/panels/", portfolio_views.fragment, name="dashboard-fragment"),
    path("api/v1/dashboard/", portfolio_views.api_dashboard, name="api-dashboard"),
    path(
        "operations/dead-letter/<int:pk>/resolve/",
        operation_views.resolve_dead_letter,
        name="operations-resolve-dead-letter",
    ),
    path("alerts/", alert_views.center, name="alerts"),
    path("alerts/new/", alert_views.edit, name="alert-new"),
    path("alerts/<int:pk>/edit/", alert_views.edit, name="alert-edit"),
    path("alerts/<int:pk>/disable/", alert_views.disable, name="alert-disable"),
    path("api/v1/alerts/", alert_views.api_list, name="api-alerts"),
    path("notifications/", notification_views.center, name="notifications"),
    path(
        "notifications/preferences/",
        notification_views.preferences,
        name="notification-preferences",
    ),
    path("api/v1/notifications/", notification_views.api_list, name="api-notifications"),
    path("api/v1/notifications/<int:pk>/read/", notification_views.read, name="notification-read"),
    path(
        "api/v1/notifications/browser-claim/",
        notification_views.browser_claim,
        name="notification-browser-claim",
    ),
    path("operations/", operation_views.center, name="operations"),
    path("operations/<int:pk>/control/", operation_views.control, name="operations-control"),
    path("api/v1/operations/health/", operation_views.api_health, name="api-operations-health"),
    path("", views.home, name="home"),
    path("auth/login/", account_views.SignInView.as_view(), name="login"),
    path("auth/logout/", account_views.sign_out, name="logout"),
    path("auth/password-reset/", account_views.password_reset_request, name="password-reset"),
    path(
        "auth/password-reset/sent/", account_views.password_reset_sent, name="password-reset-sent"
    ),
    path(
        "auth/password-reset/complete/",
        account_views.password_reset_complete,
        name="password-reset-complete",
    ),
    path(
        "auth/password-reset/<str:token>/",
        account_views.password_reset_confirm,
        name="password-reset-confirm",
    ),
    path("settings/profile/", account_views.profile, name="profile"),
    path(
        "settings/trading/",
        account_views.trading_preferences,
        name="trading-preferences",
    ),
    path("settings/security/audit/", account_views.audit_events, name="audit-events"),
    path("settings/security/sessions/", account_views.sessions, name="sessions"),
    path(
        "settings/security/sessions/<int:session_id>/revoke/",
        account_views.revoke_session,
        name="revoke-session",
    ),
    path("api/v1/me/", account_views.api_me, name="api-me"),
    path("api/v1/exchanges/", exchange_views.api_exchanges, name="api-exchanges"),
    path("api/v1/markets/search/", market_views.api_search, name="api-market-search"),
    path("api/v1/markets/quotes/", market_views.api_quotes, name="api-market-quotes"),
    path("api/v1/markets/stream/", market_views.api_stream, name="api-market-stream"),
    path(
        "api/v1/exchange-accounts/<int:pk>/",
        exchange_views.api_exchange_account,
        name="api-exchange-account",
    ),
    path(
        "api/v1/me/trading-preferences/",
        account_views.api_trading_preferences,
        name="api-trading-preferences",
    ),
    path("dashboard/", portfolio_views.dashboard, name="dashboard"),
    path("paper/", paper_views.list_trades, name="paper-trades"),
    path("paper/<int:pk>/", paper_views.trade_detail, name="paper-trade-detail"),
    path("paper/launch/<int:plan_id>/", paper_views.launch_trade, name="paper-launch"),
    path("paper/<int:pk>/cancel/", paper_views.cancel_trade, name="paper-cancel"),
    path("paper/risk/", paper_risk_views.paper_risk, name="paper-risk"),
    path("api/v1/paper/trades/", paper_views.api_trades, name="api-paper-trades"),
    path("api/v1/paper/trades/<int:pk>/", paper_views.api_trade_detail, name="api-paper-detail"),
    path("inbox/", inbox_views.inbox, name="inbox"),
    path("inbox/receive/", inbox_views.receive, name="inbox-receive"),
    path("smart-paste/", inbox_views.smart_paste, name="smart-paste"),
    path("api/v1/smart-paste/", inbox_views.api_smart_paste, name="api-smart-paste"),
    path("inbox/<int:pk>/", inbox_views.detail, name="inbox-detail"),
    path("inbox/<int:pk>/edit/", inbox_views.edit, name="inbox-edit"),
    path("inbox/<int:pk>/action/", inbox_views.action, name="inbox-action"),
    path("api/v1/inbox/", inbox_views.api_list, name="api-inbox"),
    path("api/v1/inbox/receive/", inbox_views.api_receive, name="api-inbox-receive"),
    path("api/v1/inbox/<int:pk>/", inbox_views.api_detail, name="api-inbox-detail"),
    path("api/v1/inbox/<int:pk>/edit/", inbox_views.api_edit, name="api-inbox-edit"),
    path("api/v1/inbox/<int:pk>/action/", inbox_views.api_action, name="api-inbox-action"),
    path("api/v1/manual/context/", trade_context.manual_context, name="manual-context"),
    path("api/v1/manual/plans/", plan_views.api_create, name="api-manual-create"),
    path("api/v1/manual/plans/<int:pk>/", plan_views.api_plan, name="api-manual-detail"),
    path(
        "api/v1/manual/plans/<int:pk>/confirm/", plan_views.api_confirm, name="api-manual-confirm"
    ),
    path("api/v1/manual/plans/<int:pk>/edit/", plan_views.api_edit, name="api-manual-edit"),
    path("manual/", plan_views.list_plans, name="manual-list"),
    path("manual/new/", plan_views.new_plan, name="manual-new"),
    path("manual/<int:pk>/", plan_views.preview_plan, name="manual-preview"),
    path("manual/<int:pk>/edit/", plan_views.edit_plan, name="manual-edit"),
    path("manual/<int:pk>/confirm/", plan_views.confirm_plan, name="manual-confirm"),
    path("watchlist/", watchlist_views.watchlist_page, name="watchlists"),
    path("watchlist/create/", watchlist_views.create_watchlist, name="watchlist-create"),
    path("watchlist/<int:pk>/add/", watchlist_views.add_watchlist_item, name="watchlist-add"),
    path(
        "watchlist/<int:pk>/refresh/<int:market_id>/",
        watchlist_views.request_market_refresh,
        name="watchlist-refresh",
    ),
    path(
        "watchlist/<int:pk>/remove/<int:item_id>/",
        watchlist_views.remove_watchlist_item,
        name="watchlist-remove",
    ),
    path("api/v1/watchlists/<int:pk>/", watchlist_views.api_watchlist, name="api-watchlist"),
    path("exchanges/", exchange_views.exchange_center, name="exchange-center"),
    path("exchanges/add/", exchange_views.add_exchange_account, name="exchange-account-add"),
    path(
        "exchanges/<int:pk>/",
        exchange_views.exchange_account_detail,
        name="exchange-account-detail",
    ),
    path(
        "exchanges/<int:pk>/sync/",
        exchange_views.request_account_sync,
        name="exchange-account-sync",
    ),
    path(
        "exchanges/<int:pk>/disable/",
        exchange_views.disable_exchange_account,
        name="exchange-account-disable",
    ),
    path("system/", views.system, name="system"),
    path("system/status/", views.system_status, name="system-status"),
    path("system/probe/", views.create_probe, name="create-probe"),
    path("system/probe/<uuid:probe_id>/", views.probe_status, name="probe-status"),
    path("paper/<int:pk>/stop/", paper_views.move_stop, name="paper-stop"),
    path("api/v1/paper/<int:pk>/stop/", paper_views.api_move_stop, name="api-paper-stop"),
    path("paper/<int:pk>/scenario/", paper_views.set_paper_scenario, name="paper-scenario"),
    path("paper/<int:pk>/tick/", paper_views.paper_price_event, name="paper-tick"),
    path("paper/<int:pk>/trailing/", paper_views.set_trailing, name="paper-trailing"),
    path("api/v1/paper/<int:pk>/tick/", paper_views.api_paper_tick, name="api-paper-tick"),
    path(
        "api/v1/paper/<int:pk>/trailing/",
        paper_views.api_trailing_update,
        name="api-paper-trailing",
    ),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
