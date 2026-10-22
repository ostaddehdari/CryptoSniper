from apps.accounts import views as account_views
from apps.alerts import notifications as notification_views
from apps.alerts import views as alert_views
from apps.core import views
from apps.core import react_views
from apps.core.health import dependency_status
from apps.exchanges import views as exchange_views
from apps.marketdata import views as market_views
from apps.marketdata import watchlists as watchlist_views
from apps.operations import views as operation_views
from apps.portfolio import external_views
from apps.portfolio import views as portfolio_views
from apps.reports import views as report_views
from apps.signals import views as inbox_views
from apps.tradeplans import context as trade_context
from apps.tradeplans import views as plan_views
from django.http import JsonResponse
from django.urls import path


def live(request):
    return JsonResponse({"status": "ok", "service": "cryptosniper", "stage": "S26"})


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
    path("app/", react_views.react_app, name="react-app"),
    path("api/v1/ui/bootstrap/", react_views.api_bootstrap, name="api-ui-bootstrap"),
    path("api/v1/security/step-up/", react_views.api_step_up, name="api-step-up"),
    path("api/v1/ui/favorites/", react_views.api_favorites, name="api-ui-favorites"),
    path("api/v1/ui/watchlists/", react_views.api_watchlists_ui, name="api-ui-watchlists"),
    path("api/v1/ui/manual-plans/", react_views.api_manual_plans_ui, name="api-ui-manual-plans"),
    path("api/v1/ui/signal-sources/", react_views.api_signal_sources_ui, name="api-ui-signal-sources"),
    path("api/v1/ui/notification-preferences/", react_views.api_notification_preferences_ui, name="api-ui-notification-preferences"),
    path("api/v1/ui/security/", react_views.api_security_state_ui, name="api-ui-security"),
    path("api/v1/wallets/", react_views.api_wallets, name="api-wallets"),
    path("api/v1/exchange-connections/", react_views.api_exchange_create, name="api-exchange-create"),
    path("api/v1/wallets/<int:pk>/", react_views.api_wallet_detail, name="api-wallet-detail"),
    path("api/v1/exchange-accounts/<int:pk>/markets/", react_views.api_account_markets, name="api-account-markets"),
    path("api/v1/exchange-accounts/<int:pk>/diagnostics/", react_views.api_exchange_diagnostics, name="api-exchange-diagnostics"),
    path("api/v1/exchange-accounts/<int:pk>/sync/", react_views.api_exchange_sync, name="api-exchange-sync"),
    path("api/v1/exchange-accounts/<int:pk>/rotate/", react_views.api_exchange_rotate, name="api-exchange-rotate"),
    path("api/v1/exchange-accounts/<int:pk>/revoke/", react_views.api_exchange_revoke, name="api-exchange-revoke"),
    path("api/v1/risk/fix-loss/", react_views.api_fix_loss, name="api-fix-loss"),
    path("api/v1/markets/<int:pk>/candles/", react_views.api_market_candles, name="api-market-candles"),
    path("api/v1/live-orders/", react_views.api_live_orders, name="api-live-orders"),
    path("api/v1/telegram/state/", react_views.api_telegram_state, name="api-telegram-state"),
    path("api/v1/telegram/messages/", react_views.api_telegram_messages, name="api-telegram-messages"),
    path("api/v1/telegram/action/", react_views.api_telegram_action, name="api-telegram-action"),
    path("manifest.webmanifest", views.web_manifest, name="web-manifest"),
    path("service-worker.js", views.service_worker, name="service-worker"),
    path("reports/", react_views.legacy_react_page, {"page": "reports"}, name="reports"),
    path("reports/export.csv", report_views.export_csv, name="report-csv"),
    path("reports/chart.svg", report_views.export_chart, name="report-chart"),
    path("api/v1/reports/", report_views.api_report, name="api-reports"),
    path("external/<int:pk>/", external_views.detail, name="external-detail"),
    path("dashboard/panels/", portfolio_views.fragment, name="dashboard-fragment"),
    path("api/v1/dashboard/", portfolio_views.api_dashboard, name="api-dashboard"),
    path(
        "operations/dead-letter/<int:pk>/resolve/",
        operation_views.resolve_dead_letter,
        name="operations-resolve-dead-letter",
    ),
    path("alerts/", react_views.legacy_react_page, {"page": "alerts"}, name="alerts"),
    path("alerts/new/", react_views.legacy_react_page, {"page": "alerts"}, name="alert-new"),
    path("alerts/<int:pk>/edit/", react_views.legacy_react_page, {"page": "alerts"}, name="alert-edit"),
    path("alerts/<int:pk>/disable/", alert_views.disable, name="alert-disable"),
    path("api/v1/alerts/", alert_views.api_list, name="api-alerts"),
    path("notifications/", react_views.legacy_react_page, {"page": "alerts"}, name="notifications"),
    path(
        "notifications/preferences/",
        react_views.legacy_react_page,
        {"page": "settings"},
        name="notification-preferences",
    ),
    path("api/v1/notifications/", notification_views.api_list, name="api-notifications"),
    path("api/v1/notifications/<int:pk>/read/", notification_views.read, name="notification-read"),
    path(
        "api/v1/notifications/browser-claim/",
        notification_views.browser_claim,
        name="notification-browser-claim",
    ),
    path("operations/", react_views.legacy_react_page, {"page": "operations"}, name="operations"),
    path("operations/<int:pk>/control/", operation_views.control, name="operations-control"),
    path("api/v1/operations/health/", operation_views.api_health, name="api-operations-health"),
    path("api/v1/operations/accounts/<int:pk>/control/", operation_views.api_control, name="api-operations-account-control"),
    path("api/v1/acceptance/", operation_views.api_acceptance, name="api-acceptance"),
    path(
        "api/v1/operations/host-capabilities/",
        operation_views.api_host_capabilities,
        name="api-host-capabilities",
    ),
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
    path("settings/profile/", react_views.legacy_react_page, {"page": "settings"}, name="profile"),
    path(
        "settings/trading/",
        react_views.legacy_react_page,
        {"page": "settings"},
        name="trading-preferences",
    ),
    path("settings/security/audit/", react_views.legacy_react_page, {"page": "settings"}, name="audit-events"),
    path(
        "settings/security/step-up/",
        account_views.security_step_up,
        name="security-step-up",
    ),
    path("settings/security/sessions/", react_views.legacy_react_page, {"page": "settings"}, name="sessions"),
    path(
        "settings/security/sessions/<int:session_id>/revoke/",
        account_views.revoke_session,
        name="revoke-session",
    ),
    path("api/v1/me/", account_views.api_me, name="api-me"),
    path("api/v1/exchanges/", exchange_views.api_exchanges, name="api-exchanges"),
    path("api/v1/markets/search/", market_views.api_search, name="api-market-search"),
    path("api/v1/markets/quotes/", market_views.api_quotes, name="api-market-quotes"),
    path(
        "api/v1/markets/public-prices/",
        market_views.api_public_prices,
        name="api-public-prices",
    ),
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
    path("dashboard/", react_views.legacy_react_page, {"page": "dashboard"}, name="dashboard"),
    path("paper/", react_views.paper_mode_removed, name="paper-trades"),
    path("paper/<int:pk>/", react_views.paper_mode_removed, name="paper-trade-detail"),
    path("paper/launch/<int:plan_id>/", react_views.paper_mode_removed, name="paper-launch"),
    path("paper/<int:pk>/status/", react_views.paper_mode_removed, name="paper-status"),
    path("paper/<int:pk>/close/", react_views.paper_mode_removed, name="paper-close"),
    path("paper/<int:pk>/cancel/", react_views.paper_mode_removed, name="paper-cancel"),
    path("paper/risk/", react_views.paper_mode_removed, name="paper-risk"),
    path("api/v1/paper/trades/", react_views.paper_mode_removed, name="api-paper-trades"),
    path("api/v1/paper/trades/<int:pk>/", react_views.paper_mode_removed, name="api-paper-detail"),
    path("inbox/", react_views.legacy_react_page, {"page": "inbox"}, name="inbox"),
    path("settings/sources/", react_views.legacy_react_page, {"page": "settings"}, name="source-settings"),
    path("settings/telegram/", react_views.legacy_react_page, {"page": "telegram"}, name="telegram-settings"),
    path(
        "settings/telegram/channels/<int:pk>/",
        react_views.legacy_react_page,
        {"page": "telegram"},
        name="telegram-channel-analytics",
    ),
    path(
        "api/v1/telegram/channels/<int:pk>/analytics/",
        inbox_views.api_telegram_channel_analytics,
        name="api-telegram-channel-analytics",
    ),
    path("inbox/receive/", inbox_views.receive, name="inbox-receive"),
    path("smart-paste/", react_views.legacy_react_page, {"page": "newtrade"}, name="smart-paste"),
    path("api/v1/smart-paste/", inbox_views.api_smart_paste, name="api-smart-paste"),
    path("inbox/<int:pk>/", react_views.legacy_react_page, {"page": "inbox"}, name="inbox-detail"),
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
    path("manual/", react_views.legacy_react_page, {"page": "trades"}, name="manual-list"),
    path("manual/new/", react_views.legacy_react_page, {"page": "newtrade"}, name="manual-new"),
    path("manual/<int:pk>/", react_views.legacy_react_page, {"page": "newtrade"}, name="manual-preview"),
    path("manual/<int:pk>/edit/", react_views.legacy_react_page, {"page": "newtrade"}, name="manual-edit"),
    path("manual/<int:pk>/confirm/", plan_views.confirm_plan, name="manual-confirm"),
    path("watchlist/", react_views.legacy_react_page, {"page": "settings"}, name="watchlists"),
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
    path("exchanges/", react_views.legacy_react_page, {"page": "exchanges"}, name="exchange-center"),
    path("exchanges/add/", react_views.legacy_react_page, {"page": "exchanges"}, name="exchange-account-add"),
    path(
        "exchanges/<int:pk>/",
        react_views.legacy_react_page,
        {"page": "exchanges"},
        name="exchange-account-detail",
    ),
    path(
        "exchanges/<int:pk>/sync/",
        exchange_views.request_account_sync,
        name="exchange-account-sync",
    ),
    path(
        "exchanges/<int:pk>/live-order/",
        exchange_views.submit_live_spot_order,
        name="exchange-live-order",
    ),
    path(
        "exchanges/<int:pk>/disable/",
        exchange_views.disable_exchange_account,
        name="exchange-account-disable",
    ),
    path(
        "exchanges/<int:pk>/rotate/",
        exchange_views.rotate_exchange_account,
        name="exchange-account-rotate",
    ),
    path(
        "exchanges/<int:pk>/revoke/",
        exchange_views.revoke_exchange_account,
        name="exchange-account-revoke",
    ),
    path("system/", react_views.legacy_react_page, {"page": "operations"}, name="system"),
    path("system/status/", views.system_status, name="system-status"),
    path("api/v1/engine/readiness/", views.api_engine_readiness, name="api-engine-readiness"),
    path(
        "api/v1/deployment/readiness/",
        views.api_deployment_readiness,
        name="api-deployment-readiness",
    ),
    path("system/probe/", views.create_probe, name="create-probe"),
    path("system/probe/<uuid:probe_id>/", views.probe_status, name="probe-status"),
    path("paper/<int:pk>/stop/", react_views.paper_mode_removed, name="paper-stop"),
    path("api/v1/paper/<int:pk>/stop/", react_views.paper_mode_removed, name="api-paper-stop"),
    path("paper/<int:pk>/scenario/", react_views.paper_mode_removed, name="paper-scenario"),
    path("paper/<int:pk>/tick/", react_views.paper_mode_removed, name="paper-tick"),
    path("paper/<int:pk>/trailing/", react_views.paper_mode_removed, name="paper-trailing"),
    path("api/v1/paper/<int:pk>/tick/", react_views.paper_mode_removed, name="api-paper-tick"),
    path(
        "api/v1/paper/<int:pk>/trailing/",
        react_views.paper_mode_removed,
        name="api-paper-trailing",
    ),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
