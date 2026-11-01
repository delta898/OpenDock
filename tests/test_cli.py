"""Checks for the public CLI without starting Docker or contacting Cloudflare."""

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_loader("opendock_cli", loader=None)
cli = importlib.util.module_from_spec(spec)
cli.__file__ = str(ROOT / "opendock")
exec(compile((ROOT / "opendock").read_text(), str(ROOT / "opendock"), "exec"), cli.__dict__)

config_spec = importlib.util.spec_from_file_location(
    "opendock_config", ROOT / "scripts" / "opendock-config.py"
)
config_setup = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(config_setup)


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
            self.assertIn("remove hermes --dry-run", result.stdout)
            self.assertIn("service wordpress multisite", result.stdout)
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

    def test_remove_is_registered_and_scoped_to_one_service(self):
        parsed = cli.parser().parse_args(["remove", "hermes", "--dry-run"])
        self.assertEqual(parsed.command, "remove")
        self.assertEqual(parsed.target, "hermes")
        self.assertTrue(parsed.dry_run)

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

    def test_sync_dry_run_includes_worktree_files_and_previews_pruning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / ".sync.env.toml"
            config.write_text(
                '[targets.test]\nremote = "user@example.test"\n'
                'path = "/srv/opendock"\nssh_port = 2200\n'
            )
            with mock.patch.object(cli, "SYNC_CONFIG", config), \
                 mock.patch.object(cli, "run") as run, \
                 mock.patch.object(cli, "remote_sync_prune", return_value=b"preview\n") as remote_prune:
                cli.sync("test", dry_run=True)
        arguments = run.call_args.args
        self.assertIn("--dry-run", arguments)
        self.assertIn("--files-from=-", arguments)
        self.assertIn("--checksum", arguments)
        self.assertNotIn("--delete", arguments)
        self.assertIn("--exclude=domains.conf", arguments)
        self.assertEqual(arguments[-1], "user@example.test:/srv/opendock/")
        self.assertEqual(run.call_args.kwargs["env"]["RSYNC_RSH"], "ssh -p 2200")
        self.assertTrue(run.call_args.kwargs["input_data"])
        self.assertIn(b"static-sites/README.md", run.call_args.kwargs["input_data"])
        remote_prune.assert_called_once()
        self.assertEqual(remote_prune.call_args.args[3], "preview")

    def test_multiple_hostnames_require_explicit_hostname(self):
        routes = [{"hostname": host, "type": "docker", "target": "wordpress"}
                  for host in ("blog.example.com", "blog.example.org")]
        with mock.patch.object(cli, "domains_module") as domains:
            domains.return_value.resolve_routes.return_value = routes
            with self.assertRaisesRegex(cli.CLIError, "multiple hostnames"):
                cli.launch("wordpress")

    def test_hermes_model_probe_leaves_compose_progress_visible(self):
        with mock.patch.object(cli, "compose", return_value='default: "openai/gpt-4o"') as compose:
            self.assertTrue(cli.hermes_model_is_configured())
        self.assertEqual(
            compose.call_args.args,
            ("hermes", "run", "--rm", "--no-deps", "hermes", "config", "get", "model"),
        )
        self.assertTrue(compose.call_args.kwargs["capture"])
        self.assertFalse(compose.call_args.kwargs.get("quiet", False))

    def test_fresh_hermes_volume_runs_onboarding_without_model_probe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config" / "core.env").touch()
            settings = mock.Mock()
            output = io.StringIO()
            with mock.patch.object(cli, "ROOT", root), \
                 mock.patch.object(cli, "settings_module", return_value=settings), \
                 mock.patch.object(cli, "check_config"), \
                 mock.patch.object(cli, "lifecycle"), \
                 mock.patch.object(cli, "hermes_data_volume_exists", return_value=False), \
                 mock.patch.object(cli, "hermes_model_is_configured", return_value=True) as probe, \
                 mock.patch.object(cli, "compose") as compose, \
                 redirect_stdout(output):
                cli.ensure_hermes_ready()

        probe.assert_called_once_with()
        compose.assert_called_once_with("hermes", "run", "--rm", "hermes", "setup")
        self.assertIn("first-run onboarding required", output.getvalue())

    def test_hermes_dashboard_password_is_a_masked_user_secret(self):
        field = next(item for item in config_setup.CONFIG_FIELDS["hermes"]
                     if item.name == "HERMES_DASHBOARD_PASSWORD")
        self.assertEqual(field.kind, "secret-user")
        with mock.patch.object(config_setup, "is_real_value", return_value=False), \
             mock.patch.object(config_setup.getpass, "getpass", return_value="chosen-secret") as prompt:
            self.assertEqual(config_setup.prompt_secret(field, {}), "chosen-secret")
        prompt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
