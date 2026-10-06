from unittest.mock import patch

import pytest
from apps.core.models import ServiceProbe
from apps.core.tasks import infrastructure_probe


@pytest.mark.django_db
def test_probe_receipt_is_idempotent():
    probe = ServiceProbe.objects.create(queue="orders")
    first = infrastructure_probe.run(str(probe.pk))
    with patch("apps.core.tasks.os.getpid", return_value=first["worker_pid"] + 1000):
        duplicate = infrastructure_probe.run(str(probe.pk))
    assert duplicate == first
    assert ServiceProbe.objects.filter(pk=probe.pk, status="succeeded").count() == 1
