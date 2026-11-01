"""Checks for the public CLI without starting Docker or contacting Cloudflare."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_loader("opendock_cli", loader=None)
cli = importlib.util.module_from_spec(spec)
cli.__file__ = str(ROOT / "opendock")
exec(compile((ROOT / "opendock").read_text(), str(ROOT / "opendock"), "exec"), cli.__dict__)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "opendock"), *args], cwd=ROOT,
        text=True, capture_output=True, check=True,
    )


class CLITests(unittest.TestCase):
    def test_help_shows_current_workflows_and_generic_route_examples(self):
        for args in ((), ("--help",), ("help",)):
            result = run_cli(*args)
            self.assertIn("Start here", result.stdout)
            self.assertIn("./opendock list", result.stdout)
            self.assertIn("./opendock launch <service>", result.stdout)
            self.assertIn("route add <hostname> <service|static>", result.stdout)
            self.assertIn("route add docs.example.org static", result.stdout)
            self.assertIn("remove <service> --dry-run", result.stdout)
            self.assertIn("service <service> <command>", result.stdout)
            self.assertIn("Services that declare email support", result.stdout)
            self.assertNotIn("service wordpress multisite", result.stdout)
            self.assertNotIn("service hermes onboard", result.stdout)
            self.assertNotIn("positional arguments:", result.stdout)
            self.assertLess(result.stdout.index("./opendock setup"),
                            result.stdout.index("./opendock route add"))

    def test_help_is_available_at_each_command_level(self):
        route_help = run_cli("route", "--help")
        self.assertIn("Add, show, or remove mappings", route_help.stdout)

        route_add_help = run_cli("route", "add", "--help")
        self.assertIn("Full public hostname", route_add_help.stdout)
        self.assertIn("or static", route_add_help.stdout)
        self.assertIn("static-sites/<hostname>/", route_add_help.stdout)

        setup_help = run_cli("setup", "--help")
        self.assertIn("shared config (such as mail)", setup_help.stdout)
        self.assertIn("./opendock setup mail", setup_help.stdout)

        service_help = run_cli("service", "hermes", "--help")
        self.assertIn("onboard", service_help.stdout)
        self.assertIn("interactive model and provider setup wizard", service_help.stdout)

        onboard_help = run_cli("service", "hermes", "onboard", "--help")
        self.assertIn("performs onboarding automatically", onboard_help.stdout)

        wordpress_help = run_cli("service", "wordpress", "multisite", "--help")
        self.assertIn("requires a migration", wordpress_help.stdout)

    def test_service_list_and_make_compatibility_match(self):
        direct = run_cli("list", "services")
        legacy = subprocess.run(
            ["make", "list", "services"], cwd=ROOT, text=True,
            capture_output=True, check=True,
        )
        self.assertEqual(direct.stdout, legacy.stdout)
        self.assertIn("wordpress", direct.stdout)

    def test_bad_arguments_fail_before_changes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "opendock"), "route", "add", "example.com"],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("service", result.stderr)

    def test_remove_is_registered_and_scoped_to_one_service(self):
        parsed = cli.parser().parse_args(["remove", "hermes", "--dry-run"])
        self.assertEqual(parsed.command, "remove")
        self.assertEqual(parsed.target, "hermes")
        self.assertTrue(parsed.dry_run)

    def test_docker_launch_sequence_passes_started_dependencies(self):
        route = {"hostname": "blog.example.com", "type": "docker", "target": "wordpress"}
        with mock.patch.object(cli, "domains_module") as domains, \
             mock.patch.object(cli, "launch_service_set", return_value={"infra"}) as start_deps, \
             mock.patch.object(cli, "lifecycle") as lifecycle, \
             mock.patch.object(cli, "post_launch") as post_launch, \
             mock.patch.object(cli, "reload_gateway") as gateway, \
             mock.patch.object(cli, "publish") as publish:
            domains.return_value.resolve_routes.return_value = [route]
            cli.launch("blog.example.com")
        start_deps.assert_called_once_with(["wordpress"])
        lifecycle.assert_called_once_with("up", "wordpress", already_started={"infra"})
        post_launch.assert_called_once_with("wordpress")
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
                 mock.patch.object(cli, "remote_sync_prune", return_value=b"preview\n") as prune:
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
        prune.assert_called_once()
        self.assertEqual(prune.call_args.args[3], "preview")

    def test_multiple_hostnames_require_explicit_hostname(self):
        routes = [{"hostname": host, "type": "docker", "target": "wordpress"}
                  for host in ("blog.example.com", "blog.example.org")]
        with mock.patch.object(cli, "domains_module") as domains:
            domains.return_value.resolve_routes.return_value = routes
            with self.assertRaisesRegex(cli.CLIError, "multiple hostnames"):
                cli.launch("wordpress")

    def test_hermes_prepare_skips_when_existing_model_is_configured(self):
        service = cli.ServiceCatalog(ROOT).get("hermes")
        compose = mock.Mock()
        compose.named_volume_exists.return_value = True
        compose.run.return_value = 'default: "openai/gpt-6"'
        messages = []
        context = cli.ServiceContext(
            service=service, settings={}, compose=compose, report=messages.append,
        )

        result = cli.prepare_service(context)

        self.assertEqual(result.status, "not_needed")
        self.assertIn("onboarding already complete", result.message)
        compose.run.assert_called_once_with(
            "run", "--rm", "--no-deps", "hermes", "config", "get", "model",
            capture=True,
        )
        self.assertIn("checking onboarding status", messages)

    def test_hermes_prepare_runs_onboarding_for_fresh_volume(self):
        service = cli.ServiceCatalog(ROOT).get("hermes")
        compose = mock.Mock()
        compose.named_volume_exists.return_value = False
        compose.run.side_effect = [None, 'default: "openai/gpt-6"']
        messages = []
        context = cli.ServiceContext(
            service=service, settings={}, compose=compose, report=messages.append,
        )

        result = cli.prepare_service(context)

        self.assertEqual(result.status, "completed")
        self.assertEqual(compose.run.call_args_list, [
            mock.call("run", "--rm", "hermes", "setup"),
            mock.call("run", "--rm", "--no-deps", "hermes", "config", "get", "model",
                      capture=True),
        ])
        self.assertIn("first-run onboarding", messages)

    def test_hermes_dashboard_password_is_declared_as_private_user_input(self):
        service = cli.ServiceCatalog(ROOT).get("hermes")
        field = next(item for item in service.setup_fields
                     if item["name"] == "HERMES_DASHBOARD_PASSWORD")
        self.assertEqual(field["kind"], "secret-user")
        self.assertIn("not displayed", field["note"])


if __name__ == "__main__":
    unittest.main()
