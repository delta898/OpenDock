"""Tests for descriptor-driven removal planning and its destructive-action guard."""

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "opendock_remove", ROOT / "scripts" / "opendock-remove.py"
)
remove = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remove)


class FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class FakeDomains:
    def __init__(self, routes):
        self.DOMAINS_FILE = Path("/tmp/domains.conf")
        self.routes = list(routes)
        self.saved = None
        self.rendered = None

    def parse_domains_file(self):
        return list(self.routes)

    def default_routes(self):
        return list(self.routes)

    def save_routes(self, routes):
        self.saved = list(routes)

    def render_routes(self, routes):
        self.rendered = list(routes)


def removal_plan(*, routes=None, shared_database=None):
    definition = SimpleNamespace(name="example", display_name="Example")
    return {
        "service": definition,
        "domains": FakeDomains(routes or []),
        "routes": routes or [],
        "compose_ids": ["compose-container"],
        "orphan_containers": [],
        "volumes": [],
        "images": [],
        "data_paths": [],
        "preserve_paths": [],
        "config_files": [],
        "shared_database": shared_database,
        "configured_keys": [],
        "remove_service_config": False,
        "migrate_legacy_config": False,
    }


class RemoveTests(unittest.TestCase):
    def test_service_config_removal_keeps_restricted_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service_config = root / "services" / "example" / ".env"
            service_config.parent.mkdir(parents=True)
            service_config.write_text("EXAMPLE_PASSWORD=private-value\n")
            with mock.patch.object(remove, "ROOT", root):
                remove.remove_service_config("example")

            self.assertFalse(service_config.exists())
            backups = list(
                (root / "backups" / "config" / "services" / "example").glob(".env.*.bak")
            )
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "EXAMPLE_PASSWORD=private-value\n")
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_removal_orders_compose_and_routes_before_shared_database(self):
        events = []
        plan = removal_plan(shared_database={"database": "example_db"})

        def run(args, **kwargs):
            events.append("compose-down" if "down" in args else "compose-stop")
            return FakeResult()

        with mock.patch.object(remove, "initialize"), \
             mock.patch.object(remove, "compose_prefix", return_value=["docker", "compose"]), \
             mock.patch.object(remove, "run_command", side_effect=run), \
             mock.patch.object(remove, "remove_routes", side_effect=lambda *_: events.append("routes")), \
             mock.patch.object(remove, "remove_shared_database", side_effect=lambda *_: events.append("database")), \
             mock.patch.object(remove, "remove_service_config"), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            remove.remove_resources(plan)

        self.assertEqual(events, ["compose-stop", "compose-down", "routes", "database"])

    def test_compose_failure_preserves_routes_and_shared_database(self):
        plan = removal_plan(shared_database={"database": "example_db"})
        with mock.patch.object(remove, "initialize"), \
             mock.patch.object(remove, "compose_prefix", return_value=["docker", "compose"]), \
             mock.patch.object(remove, "run_command", side_effect=remove.RemovalError("compose failed")), \
             mock.patch.object(remove, "remove_routes") as remove_routes, \
             mock.patch.object(remove, "remove_shared_database") as remove_database:
            with self.assertRaisesRegex(remove.RemovalError, "compose failed"):
                remove.remove_resources(plan)

        remove_routes.assert_not_called()
        remove_database.assert_not_called()

    def test_route_removal_preserves_other_services(self):
        routes = [
            {"hostname": "agent.example.test", "type": "service", "target": "example"},
            {"hostname": "blog.example.test", "type": "service", "target": "wordpress"},
        ]
        domains = FakeDomains(routes)
        domains.DOMAINS_FILE = Path("/tmp/domains.conf")
        plan = removal_plan(routes=[routes[0]])
        plan["domains"] = domains

        def run(args, **kwargs):
            if args[0] == "docker":
                return FakeResult("caddy\n")
            return FakeResult()

        with mock.patch.object(remove, "routes_for_removal", return_value=routes), \
             mock.patch.object(remove, "run_command", side_effect=run) as run_command:
            remove.remove_routes("example", plan)

        self.assertEqual(domains.saved, [routes[1]])
        self.assertEqual(domains.rendered, [routes[1]])
        self.assertTrue(any("publish-cloudflare.py" in str(arg)
                            for arg in run_command.call_args_list[0].args[0]))

    def test_dry_run_and_noninteractive_invocations_never_remove(self):
        plan = removal_plan()
        with mock.patch.object(remove, "build_plan", return_value=plan), \
             mock.patch.object(remove, "print_plan"), \
             mock.patch.object(remove, "remove_resources") as remove_action, \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.main(["example", "--dry-run"]), 0)
            remove_action.assert_not_called()

        with mock.patch.object(remove, "build_plan", return_value=plan), \
             mock.patch.object(remove, "print_plan"), \
             mock.patch.object(remove, "remove_resources") as remove_action, \
             mock.patch.object(remove.sys, "stdin", mock.Mock(isatty=mock.Mock(return_value=False))), \
             mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(remove.main(["example"]), 1)
            remove_action.assert_not_called()

    def test_wrong_confirmation_cancels_without_removal(self):
        plan = removal_plan()
        with mock.patch.object(remove, "build_plan", return_value=plan), \
             mock.patch.object(remove, "print_plan"), \
             mock.patch.object(remove, "remove_resources") as remove_action, \
             mock.patch.object(remove.sys, "stdin", mock.Mock(isatty=mock.Mock(return_value=True))), \
             mock.patch("builtins.input", return_value="yes"), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.main(["example"]), 0)
            remove_action.assert_not_called()

    def test_unknown_service_fails_closed_before_docker_access(self):
        with mock.patch.object(remove, "run_command") as run_command, \
             mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(remove.main(["not-a-service"]), 1)
        run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
