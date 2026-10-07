from apps.accounts import views as account_views
from apps.core import views
from apps.core.health import dependency_status
from django.contrib.auth.views import LogoutView
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
    path("auth/login/", views.SignInView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("settings/profile/", account_views.profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("system/", views.system, name="system"),
    path("system/status/", views.system_status, name="system-status"),
    path("system/probe/", views.create_probe, name="create-probe"),
    path("system/probe/<uuid:probe_id>/", views.probe_status, name="probe-status"),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
