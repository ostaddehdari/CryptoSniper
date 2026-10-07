from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from .health import dependency_status
from .models import ServiceProbe
from .tasks import infrastructure_probe


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


@login_required
@never_cache
@require_GET
def dashboard(request):
    return render(request, "core/dashboard.html", {"nav": "dashboard"})


def system_context():
    checks = dependency_status()
    heartbeat = None
    try:
        heartbeat = cache.get("worker_heartbeat")
    except RedisError:
        pass
    seen = parse_datetime(heartbeat["seen_at"]) if heartbeat else None
    fresh = seen is not None and timezone.now() - seen < timedelta(seconds=90)
    services = [
        ("پایگاه داده", "PostgreSQL", checks["postgresql"]),
        ("حافظه موقت", "Redis", checks["redis_cache"]),
        ("صف پردازش", "Broker", checks["redis_broker"]),
        ("ذخیره نتایج", "Result backend", checks["redis_results"]),
        ("پردازش پس‌زمینه", "Worker + Scheduler", fresh),
    ]
    return {"services": services, "healthy": all(checks.values()), "worker_alive": fresh}


@login_required
@never_cache
@require_GET
def system(request):
    return render(request, "core/system.html", {"nav": "system"})


@login_required
@never_cache
@require_GET
def system_status(request):
    return render(request, "core/partials/status.html", system_context())


@login_required
@never_cache
@require_POST
def create_probe(request):
    queue = request.POST.get("queue", "orders")
    if queue not in {"orders", "reports"}:
        return HttpResponseBadRequest("صف معتبر انتخاب کنید.")
    try:
        with transaction.atomic():
            probe = ServiceProbe.objects.create(
                requested_by=request.user,
                queue=queue,
                correlation_id=request.correlation_id,
            )
            transaction.on_commit(
                lambda: infrastructure_probe.apply_async(
                    args=[str(probe.pk)],
                    queue=queue,
                    task_id=str(probe.pk),
                )
            )
    except OperationalError:
        return render(request, "core/partials/probe.html", {"error": True}, status=503)
    return render(request, "core/partials/probe.html", {"probe": probe})


@login_required
@never_cache
@require_GET
def probe_status(request, probe_id):
    probe = get_object_or_404(ServiceProbe, id=probe_id, requested_by=request.user)
    return render(request, "core/partials/probe.html", {"probe": probe})
