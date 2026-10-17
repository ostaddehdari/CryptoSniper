"""Private central notification APIs. Browser claim is explicit POST + CSRF."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.security import session_api_required

from .models import Notification, NotificationPreference


@login_required
@never_cache
@require_GET
def center(request):
    preferences, _ = NotificationPreference.objects.get_or_create(owner=request.user)
    return render(
        request,
        "alerts/notifications.html",
        {
            "nav": "notifications",
            "items": Notification.objects.filter(owner=request.user, in_app=True)[:100],
            "preferences": preferences,
        },
    )


@session_api_required
@never_cache
@require_GET
def api_list(request):
    qs = Notification.objects.filter(owner=request.user, in_app=True)
    return JsonResponse(
        {
            "unread": qs.filter(read_at__isnull=True).count(),
            "items": [
                {
                    "id": n.pk,
                    "title": n.title,
                    "body": n.body,
                    "severity": n.severity,
                    "read": n.read_at is not None,
                }
                for n in qs[:30]
            ],
        }
    )


@session_api_required
@require_POST
def read(request, pk):
    item = get_object_or_404(Notification, pk=pk, owner=request.user)
    Notification.objects.filter(pk=item.pk, read_at__isnull=True).update(read_at=timezone.now())
    if request.POST.get("return") == "page":
        return redirect("notifications")
    return JsonResponse({"read": True})


@login_required
@require_POST
def preferences(request):
    preference, _ = NotificationPreference.objects.get_or_create(owner=request.user)
    preference.in_app = request.POST.get("in_app") == "on"
    preference.browser = request.POST.get("browser") == "on"
    preference.save()
    return redirect("notifications")


@session_api_required
@never_cache
@require_POST
@transaction.atomic
def browser_claim(request):
    preference, _ = NotificationPreference.objects.get_or_create(owner=request.user)
    if not preference.browser:
        return JsonResponse({"items": []})
    rows = list(
        Notification.objects.select_for_update(skip_locked=True).filter(
            owner=request.user,
            browser=True,
            read_at__isnull=True,
            browser_delivered_at__isnull=True,
            created_at__gte=timezone.now() - timedelta(hours=24),
        )[:10]
    )
    Notification.objects.filter(pk__in=[n.pk for n in rows]).update(
        browser_delivered_at=timezone.now()
    )
    return JsonResponse({"items": [{"id": n.pk, "title": n.title, "body": n.body} for n in rows]})
