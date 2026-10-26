from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from apps.operations.readiness import engine_readiness

from .assets import asset_url
from .health import dependency_status
from .models import ServiceProbe
from .tasks import infrastructure_probe


def home(request):
    return redirect("app-shell" if request.user.is_authenticated else "login")


@login_required
@never_cache
@require_GET
def app_shell(request):
    from .react_views import react_app

    return react_app(request)


@require_GET
def web_manifest(request):
    response = JsonResponse(
        {
            "id": reverse("home"),
            "name": "CryptoSniper",
            "short_name": "CryptoSniper",
            "description": "مرکز کنترل معاملات، سیگنال‌ها و حساب‌های صرافی",
            "lang": "fa",
            "dir": "rtl",
            "start_url": reverse("app-shell"),
            "scope": reverse("home"),
            "display": "standalone",
            "background_color": "#f3f6f5",
            "theme_color": "#2f66d8",
            "icons": [
                {
                    "src": static("img/pwa-icon.svg"),
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
        },
        content_type="application/manifest+json",
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
def service_worker(request):
    assets = [
        asset_url("react/app.css"),
        asset_url("react/app.js"),
        static("js/pwa.js"),
        static("img/mark.svg"),
        static("img/pwa-icon.svg"),
    ]
    cache_version = "-".join(asset.split("=")[-1] for asset in assets[:2])
    source = (
        "'use strict';\n"
        f"const CACHE='cryptosniper-static-{cache_version}';\n"
        f"const ASSETS={assets!r};\n"
        "self.addEventListener('install',event=>event.waitUntil("
        "caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));\n"
        "self.addEventListener('activate',event=>event.waitUntil(caches.keys().then("
        "keys=>Promise.all(keys.filter(k=>k.startsWith('cryptosniper-static-')&&k!==CACHE).map(k=>caches.delete(k))))"
        ".then(()=>self.clients.claim())));\n"
        "self.addEventListener('fetch',event=>{\n"
        "  const url=new URL(event.request.url);\n"
        f"  const staticPrefix={settings.STATIC_URL!r};\n"
        "  if(event.request.method!=='GET'||url.origin!==self.location.origin||"
        "!url.pathname.startsWith(staticPrefix))return;\n"
        "  event.respondWith(caches.match(event.request).then(hit=>hit||"
        "fetch(event.request).then(response=>{\n"
        "    if(response.ok){const copy=response.clone();caches.open(CACHE)"
        ".then(cache=>cache.put(event.request,copy));}\n"
        "    return response;\n"
        "  })));\n"
        "});\n"
    )
    response = HttpResponse(source, content_type="text/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Service-Worker-Allowed"] = reverse("home")
    return response


@login_required
@never_cache
@require_GET
def dashboard(request):
    from .react_views import react_app

    return react_app(request)


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
    from apps.exchanges.models import UserExchangeAccount

    connections = (
        UserExchangeAccount.objects.for_user(request.user)
        .exclude(status=UserExchangeAccount.Status.DISABLED)
        .exclude(credentials_encrypted="")
        .select_related("exchange")
        .order_by("exchange__name", "label")
    )
    return render(
        request,
        "core/system.html",
        {
            "nav": "system",
            "engine": engine_readiness(),
            "deployment": {
                "release": settings.RELEASE_VERSION,
                "source_revision": settings.SOURCE_REVISION,
                "environment": settings.DEPLOYMENT_ENVIRONMENT,
            },
            "connections": connections,
        },
    )


@login_required
@never_cache
@require_GET
def api_engine_readiness(request):
    response = JsonResponse(engine_readiness())
    response["Cache-Control"] = "no-store"
    return response


@login_required
@never_cache
@require_GET
def api_deployment_readiness(request):
    from .deployment import deployment_status

    report = deployment_status()
    response = JsonResponse(report, status=200 if report["status"] == "ready" else 503)
    response["Cache-Control"] = "no-store"
    return response


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
