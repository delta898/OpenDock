"""Checks for the public CLI without starting Docker or contacting Cloudflare."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_loader("opendock_cli", loader=None)
cli = importlib.util.module_from_spec(spec)
cli.__file__ = str(ROOT / "opendock")
exec(compile((ROOT / "opendock").read_text(), str(ROOT / "opendock"), "exec"), cli.__dict__)


class CLITests(unittest.TestCase):
    def test_help_shows_workflow_before_advanced_commands(self):
        for args in ([], ["--help"], ["help"]):
            result = subprocess.run([str(ROOT / "opendock"), *args],
                                    cwd=ROOT, text=True, capture_output=True, check=True)
            self.assertIn("Start here", result.stdout)
            self.assertIn("Domains and static sites", result.stdout)
            self.assertIn("Docker operations", result.stdout)
            self.assertIn("route add blog.example.org wordpress", result.stdout)
            self.assertIn("route add docs.example.org static", result.stdout)
            self.assertIn("action wordpress → multisite", result.stdout)
            self.assertLess(result.stdout.index("./opendock setup"),
                            result.stdout.index("./opendock route add"))
            self.assertNotIn("positional arguments:", result.stdout)

        route_help = subprocess.run([str(ROOT / "opendock"), "route", "add", "--help"],
                                    cwd=ROOT, text=True, capture_output=True, check=True)
        self.assertIn("blog.example.org wordpress", route_help.stdout)
        self.assertIn("docs.example.org static", route_help.stdout)
        self.assertIn("static-sites/<hostname>/", route_help.stdout)

    def test_direct_and_make_compatibility_list(self):
        direct = subprocess.run([str(ROOT / "opendock"), "list", "services"],
                                cwd=ROOT, text=True, capture_output=True, check=True)
        legacy = subprocess.run(["make", "list", "services"],
                                cwd=ROOT, text=True, capture_output=True, check=True)
        self.assertEqual(direct.stdout, legacy.stdout)
        self.assertIn("wordpress", direct.stdout)

    def test_bad_arguments_fail_before_changes(self):
        result = subprocess.run([str(ROOT / "opendock"), "route", "add", "example.com"],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("service", result.stderr)

    def test_docker_launch_sequence(self):
        route = {"hostname": "blog.example.com", "type": "docker", "target": "wordpress"}
        with mock.patch.object(cli, "domains_module") as domains, \
             mock.patch.object(cli, "lifecycle") as lifecycle, \
             mock.patch.object(cli, "post_launch") as hook, \
             mock.patch.object(cli, "reload_gateway") as gateway, \
             mock.patch.object(cli, "publish") as publish:
            domains.return_value.resolve_routes.return_value = [route]
            cli.launch("blog.example.com")
        self.assertEqual(lifecycle.call_args_list, [mock.call("up", "infra"),
                                                     mock.call("up", "wordpress")])
        hook.assert_called_once_with("wordpress")
        gateway.assert_called_once()
        publish.assert_called_once_with("blog.example.com")

    def test_sync_dry_run_keeps_host_owned_files_excluded(self):
        with mock.patch.object(cli, "ROOT", ROOT), \
             mock.patch.object(cli, "run") as run, \
             mock.patch.dict(cli.os.environ, {"SYNC_TEST_REMOTE": "user@example.test",
                                               "SYNC_TEST_PATH": "/srv/opendock"}):
            cli.sync("test", dry_run=True)
        arguments = run.call_args.args
        self.assertIn("--dry-run", arguments)
        self.assertIn("--exclude=domains.conf", arguments)
        self.assertIn("--exclude=static-sites/", arguments)
        self.assertEqual(arguments[-1], "user@example.test:/srv/opendock/")

    def test_multiple_hostnames_require_explicit_hostname(self):
        routes = [{"hostname": host, "type": "docker", "target": "wordpress"}
                  for host in ("blog.example.com", "blog.example.org")]
        with mock.patch.object(cli, "domains_module") as domains:
            domains.return_value.resolve_routes.return_value = routes
            with self.assertRaisesRegex(cli.CLIError, "multiple hostnames"):
                cli.launch("wordpress")


if __name__ == "__main__":
    unittest.main()
