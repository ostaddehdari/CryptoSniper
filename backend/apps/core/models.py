import uuid

from django.conf import settings
from django.db import models


class ServiceProbe(models.Model):
    """Infrastructure demonstration only; never places an exchange order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    correlation_id = models.UUIDField(default=uuid.uuid4)
    queue = models.CharField(max_length=16, choices=[("orders", "orders"), ("reports", "reports")])
    status = models.CharField(max_length=16, default="queued", editable=False)
    worker_pid = models.PositiveIntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["requested_by", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(queue__in=["orders", "reports"]), name="probe_queue_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["queued", "succeeded"]), name="probe_status_valid"
            ),
        ]

    def __str__(self):
        return f"{self.queue}: {self.id} ({self.status})"
