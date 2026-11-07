"""Checks for the public CLI without starting Docker or contacting Cloudflare."""

import importlib.util
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import subprocess
import sys
import tempfile
from types import SimpleNamespace
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
    def test_compose_resolves_bind_mount_from_stable_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service_root = root / "services/extensions/wordpress"
            release = service_root / "releases/0.1.0-local.1"
            release.mkdir(parents=True)
            (release / "compose.yml").write_text("services: {}\n")
            definition = SimpleNamespace(
                directory=release,
                data_directory=service_root,
                storage_mounts=({
                    "setting_key": "WORDPRESS_WEBROOT_PATH",
                },),
            )
            catalog = mock.Mock()
            catalog.names = ("wordpress",)
            catalog.get.return_value = definition
            settings = mock.Mock()
            settings.compose_env_files.return_value = []
            settings.load_values.return_value = {
                "WORDPRESS_WEBROOT_PATH": "./data/webroot",
            }
            with mock.patch.object(cli, "ROOT", root), \
                 mock.patch.object(cli, "ServiceCatalog", return_value=catalog), \
                 mock.patch.object(cli, "settings_module", return_value=settings), \
                 mock.patch.object(cli, "service_runtime_environment", return_value={}), \
                 mock.patch.object(cli, "run") as run:
                cli.compose("wordpress", "up", "-d")

        compose_env = run.call_args.kwargs["env"]
        self.assertEqual(
            compose_env["WORDPRESS_WEBROOT_PATH"],
            str(service_root / "data/webroot"),
        )
        self.assertEqual(
            run.call_args.args[1:4],
            ("compose", "--project-directory", str(release)),
        )

    def test_launch_auto_installs_and_sets_up_a_catalog_package(self):
        destination = ROOT / "services/extensions/n8n-v2/releases/0.1.0"
        catalog = {"services": [{"service_id": "n8n-v2"}]}
        output = StringIO()
        with mock.patch.dict("os.environ", {"OPENDOCK_PACKAGE_ENVIRONMENT": "dev"}), \
             mock.patch.object(cli, "fetch_catalog", return_value=(catalog, Path("cache"))) as fetch, \
             mock.patch.object(cli, "install_package", return_value=destination) as install, \
             mock.patch.object(cli.sys.stdin, "isatty", return_value=True), \
             redirect_stdout(output):
            result = cli.install_package_for_launch("n8n-v2")
        fetch.assert_called_once_with("dev")
        install.assert_called_once_with("dev", "n8n-v2", catalog, ROOT)
        self.assertIsNone(result)
        self.assertIn("continuing through prepare and launch", output.getvalue())

    def test_keyboard_interrupt_exits_cleanly(self):
        stderr = StringIO()
        with mock.patch.object(cli, "launch", side_effect=KeyboardInterrupt), \
             redirect_stderr(stderr):
            result = cli.main(["launch", "n8n-v2"])
        self.assertEqual(result, 130)
        self.assertIn("cancelled", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_launch_generates_declared_secrets_before_config_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/core.env").touch()
            settings = mock.Mock()
            with mock.patch.object(cli, "ROOT", root), \
                 mock.patch.object(cli, "settings_module", return_value=settings), \
                 mock.patch.object(cli, "check_config", side_effect=[cli.CLIError("missing"), None]) as check, \
                 mock.patch.object(cli, "script") as run_script:
                cli.ensure_service_configuration("n8n-v2")
        self.assertEqual(run_script.call_args_list[0].args,
                         ("opendock-secrets.py", "n8n-v2"))
        self.assertEqual(run_script.call_args_list[1].args,
                         ("opendock-config.py", "n8n-v2"))
        self.assertEqual(check.call_args_list, [
            mock.call("n8n-v2", quiet=True),
            mock.call("n8n-v2", quiet=True),
        ])

    def test_lifecycle_dispatch_prints_only_declared_messages(self):
        catalog = mock.Mock()
        catalog.get.side_effect = [
            SimpleNamespace(
                display_name="Example service",
                lifecycle_messages={"pre_start": "This may take a while."},
            ),
            SimpleNamespace(display_name="Plain service", lifecycle_messages={}),
        ]
        output = StringIO()
        with mock.patch.object(cli, "ServiceCatalog", return_value=catalog), \
             redirect_stdout(output):
            cli.show_lifecycle_messages(["example", "plain"], "pre_start")
        self.assertEqual(output.getvalue(), "==> Example service: This may take a while.\n")

    def test_prepare_messages_bracket_setup_prerequisites_and_prepare_action(self):
        events = []
        catalog = mock.Mock()
        catalog.get.return_value = SimpleNamespace(storage_mounts=())
        with mock.patch.object(cli, "ServiceCatalog", return_value=catalog), \
             mock.patch.object(cli, "validate_service_capabilities", side_effect=lambda _service: events.append("validate")), \
             mock.patch.object(cli, "has_capability", return_value=False), \
             mock.patch.object(cli, "show_lifecycle_messages", side_effect=lambda _items, stage: events.append(stage)), \
             mock.patch.object(cli, "ensure_service_configuration", side_effect=lambda _service: events.append("setup")), \
             mock.patch.object(cli, "script", side_effect=lambda *args: events.append("optional-setup")), \
             mock.patch.object(cli, "ensure_service_storage_configuration", side_effect=lambda _service: events.append("storage-config")), \
             mock.patch.object(cli, "prepare_service_storage", side_effect=lambda _service: events.append("storage-check")), \
             mock.patch.object(cli, "start_service_dependencies", side_effect=lambda _items, **_kwargs: events.append("dependencies") or {"infra"}), \
             mock.patch.object(cli, "run_service_preparations", side_effect=lambda _items: events.append("prepare-action")):
            started = cli.launch_service_set(["example-service"])
        self.assertEqual(started, {"infra"})
        self.assertEqual(events, [
            "validate", "pre_prepare", "setup", "optional-setup",
            "storage-config", "storage-check", "dependencies",
            "prepare-action", "post_prepare",
        ])

    def test_help_shows_current_workflows_and_generic_route_examples(self):
        for args in ((), ("--help",), ("help",)):
            result = run_cli(*args)
            self.assertIn("Start here", result.stdout)
            self.assertIn("./opendock list", result.stdout)
            self.assertIn("./opendock launch <service>", result.stdout)
            self.assertIn("route add <type> <hostname> [<target>]", result.stdout)
            self.assertIn("route add static docs.example.org", result.stdout)
            self.assertIn("route add external ai.example.org", result.stdout)
            self.assertIn("purge <service> --dry-run", result.stdout)
            self.assertIn("service <service> <command>", result.stdout)
            self.assertIn("Services that declare email support", result.stdout)
            self.assertNotIn("service wordpress multisite", result.stdout)
            self.assertNotIn("service hermes onboard", result.stdout)
            self.assertNotIn("positional arguments:", result.stdout)
            self.assertLess(result.stdout.index("./opendock setup"),
                            result.stdout.index("./opendock route add"))

    def test_help_is_available_at_each_command_level(self):
        route_help = run_cli("route", "--help")
        self.assertIn("Add, show, or remove public hostname routes", route_help.stdout)

        route_add_help = run_cli("route", "add", "--help")
        self.assertIn("Full public hostname", route_add_help.stdout)
        self.assertIn("upstream URL", route_add_help.stdout)
        self.assertIn("host.docker.internal:1234", route_add_help.stdout)
        self.assertIn("static-sites/<hostname>/", route_add_help.stdout)

        setup_help = run_cli("setup", "--help")
        self.assertIn("shared config (such as mail)", setup_help.stdout)
        self.assertIn("./opendock setup mail", setup_help.stdout)

        service_help = run_cli("service", "--help")
        self.assertIn("Installed service ID", service_help.stdout)
        self.assertIn("List a service's extra commands", service_help.stdout)

    def test_list_and_make_compatibility_match(self):
        direct = run_cli("list")
        legacy = subprocess.run(
            ["make", "list"], cwd=ROOT, text=True,
            capture_output=True, check=True,
        )
        self.assertEqual(direct.stdout, legacy.stdout)
        self.assertIn("Services:", direct.stdout)

    def test_bad_arguments_fail_before_changes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "opendock"), "route", "add", "example.com"],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("service", result.stderr)

    def test_purge_is_registered_and_scoped_to_one_service(self):
        parsed = cli.parser().parse_args(["purge", "example-service", "--dry-run"])
        self.assertEqual(parsed.command, "purge")
        self.assertEqual(parsed.target, "example-service")
        self.assertTrue(parsed.dry_run)

    def test_purge_preserves_actionable_child_error_without_python_wrapper(self):
        stderr = StringIO()

        def reject_infra(*_args, **_kwargs):
            print("OpenDock remove: Unknown service: infra", file=sys.stderr)
            return subprocess.CompletedProcess([], 1)

        with mock.patch.object(cli.subprocess, "run", side_effect=reject_infra), \
             redirect_stderr(stderr):
            result = cli.main(["purge", "infra"])
        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue().strip(), "OpenDock remove: Unknown service: infra")
        self.assertNotIn("Command failed", stderr.getvalue())

    def test_service_launch_sequence_passes_started_dependencies(self):
        route = {"hostname": "blog.example.com", "type": "service", "target": "wordpress"}
        with mock.patch.object(cli, "domains_module") as domains, \
             mock.patch.object(cli, "ensure_cloudflare_configuration") as cloudflare, \
             mock.patch.object(cli, "launch_service_set", return_value={"infra"}) as start_deps, \
             mock.patch.object(cli, "lifecycle") as lifecycle, \
             mock.patch.object(cli, "run_post_start_actions") as post_start, \
             mock.patch.object(cli, "reload_gateway") as gateway, \
             mock.patch.object(cli, "publish") as publish, \
             mock.patch.object(cli, "show_lifecycle_messages") as messages:
            domains.return_value.resolve_routes.return_value = [route]
            cli.launch("blog.example.com")
        start_deps.assert_called_once_with(["wordpress"])
        cloudflare.assert_called_once_with()
        lifecycle.assert_called_once_with(
            "up", "wordpress", already_started={"infra"}, wait=True
        )
        post_start.assert_called_once_with("wordpress")
        gateway.assert_called_once()
        publish.assert_called_once_with("blog.example.com")
        self.assertEqual(messages.call_args_list, [
            mock.call(["wordpress"], "pre_start"),
            mock.call(["wordpress"], "post_start"),
            mock.call(["wordpress"], "pre_launch"),
            mock.call(["wordpress"], "post_launch"),
        ])

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
        routes = [{"hostname": host, "type": "service", "target": "wordpress"}
                  for host in ("blog.example.com", "blog.example.org")]
        with mock.patch.object(cli, "domains_module") as domains:
            domains.return_value.resolve_routes.return_value = routes
            with self.assertRaisesRegex(cli.CLIError, "multiple hostnames"):
                cli.launch("wordpress")

if __name__ == "__main__":
    unittest.main()
