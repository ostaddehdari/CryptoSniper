import json

from django.core.management.base import BaseCommand, CommandError

from apps.operations.hosting import hosting_capabilities


class Command(BaseCommand):
    help = "Measure production-host capabilities without browser/process workarounds."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--probe-outbound", action="store_true")
        parser.add_argument("--probe-storage", action="store_true")
        parser.add_argument("--allow-incomplete", action="store_true")

    def handle(self, *args, **options):
        report = hosting_capabilities(
            probe_outbound=options["probe_outbound"],
            probe_storage=options["probe_storage"],
        )
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            for item in report["capabilities"]:
                state = "PASS" if item["ok"] else "MISSING"
                self.stdout.write(f"{state}: {item['label']} — {item['evidence']}")
        if report["status"] != "ready" and not options["allow_incomplete"]:
            raise CommandError(
                "Host capability checklist is incomplete: " + ", ".join(report["missing"])
            )
