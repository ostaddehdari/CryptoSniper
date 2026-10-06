from .base import *

DEBUG = True
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
