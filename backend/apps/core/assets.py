"""Content-versioned React assets shared by HTML and the static-only service worker."""

import hashlib
from functools import lru_cache
from pathlib import Path

from django.contrib.staticfiles import finders
from django.templatetags.static import static


@lru_cache(maxsize=32)
def _digest(path, mtime_ns, size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def asset_url(name):
    path = finders.find(name)
    if path:
        stat = Path(path).stat()
        version = _digest(str(path), stat.st_mtime_ns, stat.st_size)
        return f"{static(name)}?v={version}"
    return static(name)
