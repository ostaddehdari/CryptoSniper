from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
