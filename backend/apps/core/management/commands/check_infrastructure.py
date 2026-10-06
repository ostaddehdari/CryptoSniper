import os
import time

from django.core.management.base import BaseCommand, CommandError

from apps.core.health import dependency_status
from apps.core.models import ServiceProbe
from apps.core.tasks import infrastructure_probe


class Command(BaseCommand):
    help = "Check real PostgreSQL/Redis and execute probes on both independent worker queues."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=30)

    def handle(self, *args, **options):
        checks = dependency_status()
        if not all(checks.values()):
            raise CommandError(
                f"Unavailable dependencies: {[k for k, v in checks.items() if not v]}"
            )
        for queue in ("orders", "reports"):
            probe = ServiceProbe.objects.create(queue=queue)
            try:
                infrastructure_probe.apply_async(
                    args=[str(probe.id)], queue=queue, task_id=str(probe.id)
                )
            except Exception as error:
                raise CommandError(
                    "Could not dispatch probe; inspect worker/broker health."
                ) from error
            deadline = time.monotonic() + options["timeout"]
            while time.monotonic() < deadline:
                probe.refresh_from_db()
                if probe.status == "succeeded":
                    break
                time.sleep(0.2)
            if probe.status != "succeeded":
                raise CommandError(f"No worker receipt on {queue} within timeout.")
            if probe.worker_pid == os.getpid():
                raise CommandError("Probe ran in the caller process, not an independent worker.")
            self.stdout.write(
                self.style.SUCCESS(
                    f"PASS {queue}: database receipt, separate process, "
                    f"correlation_id={probe.correlation_id}"
                )
            )
