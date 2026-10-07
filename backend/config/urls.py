from apps.accounts import views as account_views
from apps.core import views
from apps.core.health import dependency_status
from django.http import JsonResponse
from django.urls import path


def live(request):
    return JsonResponse({"status": "ok", "service": "cryptosniper", "stage": "S01"})


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
    path(
        "api/v1/me/trading-preferences/",
        account_views.api_trading_preferences,
        name="api-trading-preferences",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("system/", views.system, name="system"),
    path("system/status/", views.system_status, name="system-status"),
    path("system/probe/", views.create_probe, name="create-probe"),
    path("system/probe/<uuid:probe_id>/", views.probe_status, name="probe-status"),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
