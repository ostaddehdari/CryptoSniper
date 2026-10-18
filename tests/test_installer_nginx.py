"""Installer regression tests with real temporary files and a fake nginx -T inventory.

Never reads/writes /etc/nginx or starts/reloads a service. Exercises the exact
embedded routing helper shipped to the operator, including plan/apply/rollback.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/cryptosniper-stage12-run.sh"


class NginxUpgradeTests(unittest.TestCase):
    installer = INSTALLER
    stage = 12

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cs-nginx-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.snippet = self.root / "nginx/snippets/cryptosniper-location.conf"
        self.snippet.parent.mkdir(parents=True)
        self.vhost = self.root / "nginx/srun.conf"
        self.plan = self.root / "plan.json"
        self.vhost.write_text(
            "server {\n listen 443 ssl;\n server_name srun.ir;\n"
            f" include {self.snippet};\n"
            " location /other-site/ { proxy_pass http://127.0.0.1:18870; }\n}\n"
        )
        source = (
            self.installer.read_text()
            .split("cat > \"$TMP_DIR/nginx-route.py\" <<'PY'\n", 1)[1]
            .split("\nPY\n", 1)[0]
        )
        source = source.replace(
            "Path('/etc/nginx/snippets/cryptosniper-location.conf')", f"Path({str(self.snippet)!r})"
        )
        self.helper = self.root / "nginx-route.py"
        self.helper.write_text(source)
        binary = self.root / "bin"
        binary.mkdir()
        nginx = binary / "nginx"
        nginx.write_text(
            "#!/usr/bin/env python3\n"
            "import os\nfrom pathlib import Path\n"
            "p=Path(os.environ['TEST_NGINX_VHOST'])\n"
            "print('# configuration file '+str(p)+':')\n"
            "print(p.read_text())\n"
        )
        nginx.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "TEST_NGINX_VHOST": str(self.vhost),
            "CONFIG_DIR": str(self.root / "private-config"),
            "WEB_PORT": "18881",
        }
        self.env.pop("NGINX_VHOST", None)

    def run_helper(self, action):
        return subprocess.run(
            [sys.executable, str(self.helper), action, str(self.plan)],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def old_snippet(self, stage):
        return (
            f"# Managed by CryptoSniper Stage{stage:02d} installer\n"
            "location ^~ /cryptosniper/ { proxy_pass http://127.0.0.1:18881/; }\n"
        )

    def test_all_prior_managed_versions_are_accepted_without_mutation(self):
        vhost = self.vhost.read_bytes()
        for stage in range(1, self.stage + 1):
            with self.subTest(stage=stage):
                previous = self.old_snippet(stage)
                self.snippet.write_text(previous)
                result = self.run_helper("plan")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.snippet.read_text(), previous)
                self.assertEqual(self.vhost.read_bytes(), vhost)

    def test_stage10_upgrade_and_rollback_preserve_other_routes(self):
        old = self.old_snippet(10)
        self.snippet.write_text(old)
        before = self.vhost.read_bytes()
        self.assertEqual(self.run_helper("plan").returncode, 0)
        result = self.run_helper("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            self.snippet.read_text().startswith(self.old_snippet(self.stage).splitlines()[0])
        )
        self.assertEqual(self.vhost.read_bytes(), before)  # Existing include is not duplicated.
        self.assertIn("/other-site/", self.vhost.read_text())
        self.assertEqual(self.run_helper("rollback").returncode, 0)
        self.assertEqual(self.snippet.read_text(), old)
        self.assertEqual(self.vhost.read_bytes(), before)

    def test_unmanaged_and_lookalike_headers_are_rejected_without_changes(self):
        for header in [
            "# manually configured",
            "# Managed by CryptoSniper Stage10 installer-custom",
            "# Managed by CryptoSniper Stage99 installer",
            "",
        ]:
            with self.subTest(header=header):
                original = header + "\nlocation /custom/ { return 200; }\n"
                self.snippet.write_text(original)
                before = self.vhost.read_bytes()
                result = self.run_helper("plan")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unmanaged CryptoSniper", result.stderr)
                self.assertEqual(self.snippet.read_text(), original)
                self.assertEqual(self.vhost.read_bytes(), before)

    def test_concurrent_snippet_edit_blocks_apply_without_overwrite(self):
        self.snippet.write_text(self.old_snippet(10))
        self.assertEqual(self.run_helper("plan").returncode, 0)
        changed = "# manually edited while installer was running\n"
        self.snippet.write_text(changed)
        before = self.vhost.read_bytes()
        result = self.run_helper("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snippet changed", result.stderr)
        self.assertEqual(self.snippet.read_text(), changed)
        self.assertEqual(self.vhost.read_bytes(), before)

    def test_concurrent_vhost_edit_blocks_apply(self):
        self.snippet.write_text(self.old_snippet(10))
        self.assertEqual(self.run_helper("plan").returncode, 0)
        changed = self.vhost.read_text() + "# concurrent edit\n"
        self.vhost.write_text(changed)
        result = self.run_helper("apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("config changed", result.stderr)
        self.assertEqual(self.vhost.read_text(), changed)
        self.assertEqual(self.snippet.read_text(), self.old_snippet(10))

    def test_first_route_install_and_rollback(self):
        before = "server { listen 443 ssl; server_name srun.ir; }\n"
        self.vhost.write_text(before)
        self.assertEqual(self.run_helper("plan").returncode, 0)
        self.assertEqual(self.run_helper("apply").returncode, 0)
        self.assertTrue(self.snippet.exists())
        self.assertEqual(self.vhost.read_text().count(f"include {self.snippet};"), 1)
        self.assertEqual(self.run_helper("rollback").returncode, 0)
        self.assertFalse(self.snippet.exists())
        self.assertEqual(self.vhost.read_text(), before)


class Stage14NginxUpgradeTests(NginxUpgradeTests):
    installer = ROOT / "scripts/cryptosniper-stage14-run.sh"
    stage = 14


class Stage16NginxUpgradeTests(NginxUpgradeTests):
    installer = ROOT / "scripts/cryptosniper-stage16-run.sh"
    stage = 16


class Stage18NginxUpgradeTests(NginxUpgradeTests):
    installer = ROOT / "scripts/cryptosniper-stage18-run.sh"
    stage = 18


if __name__ == "__main__":
    unittest.main()
