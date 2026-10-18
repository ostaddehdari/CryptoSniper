from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BASE_DIR.parent
env = environ.Env()
environ.Env.read_env(REPO_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters.")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.core",
    "apps.exchanges",
    "apps.marketdata",
    "apps.tradeplans",
    "apps.signals",
    "apps.trading",
    "apps.operations",
    "apps.alerts",
    "apps.reports",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.observability.CorrelationMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.rate_limits.RequestLimitMiddleware",
    "apps.accounts.middleware.SessionTrackingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fa"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = REPO_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
PASSWORD_RESET_TIMEOUT = 60 * 30
DEFAULT_FROM_EMAIL = "CryptoSniper <noreply@localhost>"
AUTH_LOGIN_MAX_ATTEMPTS = 5
AUTH_LOGIN_WINDOW_SECONDS = 15 * 60
REQUEST_BODY_MAX_BYTES = 256 * 1024
API_RATE_LIMIT_PER_MINUTE = 120
PARSER_RATE_LIMIT_PER_MINUTE = 10
SUBSCRIPTION_RATE_LIMIT_PER_MINUTE = 60
AUDIT_RETENTION_DAYS = 365
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
TRADING_MODE = "paper"
LIVE_TRADING_ENABLED = False
SECOND_FACTOR_PROVIDER = env("SECOND_FACTOR_PROVIDER", default="")
# Enable only when using an ASGI web process; Gunicorn WSGI uses bounded polling.
MARKETDATA_SSE_ENABLED = env.bool("MARKETDATA_SSE_ENABLED", default=False)
ENABLED_MARKET_TYPES = ("spot", "margin")
EXCHANGE_CREDENTIAL_KEYS = env.list("EXCHANGE_CREDENTIAL_KEYS", default=[])

DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("CryptoSniper requires PostgreSQL; SQLite is not supported.")
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {}).update(
    {"connect_timeout": 3, "application_name": "cryptosniper"}
)
REDIS_CACHE_URL = env("REDIS_CACHE_URL")
if urlsplit(REDIS_CACHE_URL).scheme not in {"redis", "rediss"}:
    raise ImproperlyConfigured("REDIS_CACHE_URL must use redis:// or rediss://.")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "KEY_PREFIX": "cryptosniper",
        "TIMEOUT": 300,
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
for url in (CELERY_BROKER_URL, CELERY_RESULT_BACKEND):
    if urlsplit(url).scheme not in {"redis", "rediss"}:
        raise ImproperlyConfigured("Celery requires Redis URLs.")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_DEFAULT_QUEUE = "maintenance"
CELERY_TASK_CREATE_MISSING_QUEUES = False
OPERATION_QUEUES = (
    "signals",
    "orders",
    "market_data",
    "trailing",
    "alerts",
    "reports",
    "maintenance",
)
CELERY_TASK_QUEUES = {q: {"exchange": q, "routing_key": q} for q in OPERATION_QUEUES}
CELERY_TASK_ROUTES = {
    "core.*": {"queue": "maintenance"},
    "operations.*": {"queue": "maintenance"},
    "exchanges.*": {"queue": "maintenance"},
    "marketdata.*": {"queue": "market_data"},
    "trading.close_remaining": {"queue": "orders"},
    "trading.process_paper": {"queue": "orders"},
    "trading.scan_outbox": {"queue": "maintenance"},
    "trading.monitor_paper_exits": {"queue": "trailing"},
    "trading.paper_feed_staleness": {"queue": "trailing"},
    "alerts.*": {"queue": "alerts"},
    "reports.*": {"queue": "reports"},
}
CELERY_BEAT_SCHEDULER = "apps.operations.scheduler.LeasedScheduler"
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 3
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 300}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 1,
    "socket_timeout": 3,
}
CELERY_RESULT_EXPIRES = 3600
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = 30
CELERY_TASK_TIME_LIMIT = 45
CELERY_BEAT_SCHEDULE = {
    "infrastructure-heartbeat": {
        "task": "core.worker_heartbeat",
        "schedule": 30.0,
        "options": {"queue": "maintenance", "expires": 25},
    },
}
CELERY_BEAT_SCHEDULE["refresh-performance-aggregates"] = {
    "task": "reports.refresh_aggregates",
    "schedule": 300.0,
    "options": {"queue": "reports", "expires": 240},
}
CELERY_BEAT_SCHEDULE["paper-outbox-scan"] = {
    "task": "trading.scan_outbox",
    "schedule": 12.0,
    "options": {"queue": "maintenance", "expires": 10},
}
CELERY_BEAT_SCHEDULE["paper-exit-monitor"] = {
    "task": "trading.monitor_paper_exits",
    "schedule": 12.0,
    "options": {"queue": "trailing", "expires": 10},
}
CELERY_BEAT_SCHEDULE["paper-feed-staleness"] = {
    "task": "trading.paper_feed_staleness",
    "schedule": 30.0,
    "options": {"queue": "trailing", "expires": 25},
}
CELERY_BEAT_SCHEDULE["market-display-refresh"] = {
    "task": "marketdata.refresh_watchlists",
    "schedule": 30.0,
    "options": {"queue": "market_data", "expires": 20},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.observability.RedactingJsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

CELERY_BEAT_SCHEDULE["account-recovery"] = {
    "task": "operations.recover",
    "schedule": 20.0,
    "options": {"queue": "maintenance", "expires": 18},
}
for queue_name in OPERATION_QUEUES:
    CELERY_BEAT_SCHEDULE["heartbeat-" + queue_name] = {
        "task": "operations.heartbeat",
        "schedule": 30.0,
        "args": (queue_name,),
        "options": {"queue": queue_name, "expires": 25},
    }
CELERY_BEAT_SCHEDULE["price-alerts"] = {
    "task": "alerts.evaluate",
    "schedule": 8.0,
    "options": {"queue": "alerts", "expires": 7},
}
CELERY_BEAT_SCHEDULE["portfolio-display-refresh"] = {
    "task": "marketdata.refresh_portfolio",
    "schedule": 20.0,
    "options": {"queue": "market_data", "expires": 18},
}
CELERY_BEAT_SCHEDULE["private-data-retention"] = {
    "task": "core.minimize_private_data",
    "schedule": 86400.0,
    "options": {"queue": "maintenance", "expires": 3600},
}
