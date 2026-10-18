"""Deployment identity and exact web/static readiness checks."""

from pathlib import Path

from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from .health import dependency_status


def _static_manifest():
    root = Path(settings.STATIC_ROOT)
    manifest = root / "staticfiles.json"
    return {
        "collected": root.is_dir() and manifest.is_file(),
        "manifest": "staticfiles.json" if manifest.is_file() else "missing",
    }


def _migration_state():
    executor = MigrationExecutor(connections["default"])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return {"current": not plan, "pending_count": len(plan)}


def deployment_status(*, include_migrations=False):
    dependencies = dependency_status()
    static = _static_manifest()
    migrations = _migration_state() if include_migrations else {"current": None}
    ready = all(dependencies.values()) and static["collected"]
    if include_migrations:
        ready = ready and migrations["current"]
    return {
        "status": "ready" if ready else "incomplete",
        "release": settings.RELEASE_VERSION,
        "source_revision": settings.SOURCE_REVISION,
        "runtime": "python-only",
        "node_required": False,
        "web": {
            "wsgi": settings.WSGI_APPLICATION,
            "asgi": settings.ASGI_APPLICATION,
        },
        "dependencies": dependencies,
        "static": static,
        "migrations": migrations,
    }
