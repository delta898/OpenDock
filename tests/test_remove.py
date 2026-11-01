"""Tests for service removal planning and its destructive-action guard."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
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
        self.routes = routes
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


class RemoveTests(unittest.TestCase):
    def test_build_plan_lists_hermes_owned_resources_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = root / "services" / "hermes"
            sandbox = service / "data" / "sandboxes"
            sandbox.mkdir(parents=True)
            (service / "compose.yml").write_text("services: {}\n")
            config = root / "config"
            (config / "core.env").parent.mkdir(parents=True)
            (config / "core.env").write_text("STACK_DOMAIN=example.test\n")
            service_config = service / ".env"
            service_config.parent.mkdir(parents=True, exist_ok=True)
            service_config.write_text(
                "HERMES_SUBDOMAIN=agent\nHERMES_DASHBOARD_PASSWORD=private-value\n"
            )
            service_config_example = service / ".env.default"
            service_config_example.write_text("HERMES_SUBDOMAIN=hermes\nHERMES_VERSION=v1.2.3\n")
            legacy = root / "common.env"
            legacy.write_text("STACK_DOMAIN=example.test\nHERMES_DASHBOARD_SECRET=legacy\n")
            fake_domains = FakeDomains([
                {"hostname": "agent.example.test", "type": "docker", "target": "hermes"},
                {"hostname": "blog.example.test", "type": "docker", "target": "wordpress"},
            ])
            sandbox_container = {
                "Id": "task-id",
                "Name": "/hermes-12345678",
                "Config": {"Image": "nousresearch/hermes-sandbox:desktop"},
                "Mounts": [{"Source": str(sandbox / "docker" / "root")}],
            }
            unrelated_container = {
                "Id": "other-id",
                "Name": "/other-agent",
                "Config": {"Image": "nousresearch/hermes-sandbox:desktop"},
                "Mounts": [{"Source": str(root / "other-agent-data")}],
            }

            def fake_run(args, **kwargs):
                args = [str(item) for item in args]
                if args[1:4] == ["ps", "-aq", "--filter"] and any(
                    "com.docker.compose.project=hermes" in item for item in args
                ):
                    return FakeResult("compose-id\n")
                if args[1:4] == ["ps", "-aq", "--filter"] and "label=hermes-task-id" in args:
                    return FakeResult("task-id\nother-id\ncompose-id\n")
                if args[1] == "inspect":
                    return FakeResult(json.dumps([sandbox_container, unrelated_container]))
                if args[1:3] == ["volume", "ls"]:
                    return FakeResult("hermes_hermes_data\n")
                if args[-2:] == ["config", "--images"]:
                    return FakeResult("nousresearch/hermes-agent:v1.2.3\n")
                self.fail(f"Unexpected command in fixture: {args}")

            with mock.patch.object(remove, "ROOT", root), \
                 mock.patch.object(remove, "CONFIG", config), \
                 mock.patch.object(remove, "SERVICES", root / "services"), \
                 mock.patch.object(remove, "HERMES", service), \
                 mock.patch.object(remove, "COMPOSE", service / "compose.yml"), \
                 mock.patch.object(remove, "SERVICE_CONFIG", service_config), \
                 mock.patch.object(remove, "SERVICE_CONFIG_EXAMPLE", service_config_example), \
                 mock.patch.object(remove, "LEGACY_ENV", legacy), \
                 mock.patch.object(remove, "initialize") as initialize, \
                 mock.patch.object(remove, "SANDBOX_DATA", sandbox), \
                 mock.patch.object(remove, "domains_module", return_value=fake_domains), \
                 mock.patch.object(remove, "run_command", side_effect=fake_run):
                plan = remove.build_plan()
                initialize.assert_not_called()
                self.assertTrue(plan["migrate_legacy_config"])
                self.assertEqual(
                    legacy.read_text(),
                    "STACK_DOMAIN=example.test\nHERMES_DASHBOARD_SECRET=legacy\n",
                )

        self.assertEqual([route["hostname"] for route in plan["routes"]],
                         ["agent.example.test"])
        self.assertEqual(plan["compose_ids"], ["compose-id"])
        self.assertEqual([item["id"] for item in plan["sandbox_containers"]], ["task-id"])
        self.assertEqual(plan["volumes"], ["hermes_hermes_data"])
        self.assertIn("HERMES_DASHBOARD_PASSWORD", plan["configured_keys"])
        self.assertNotIn("WORDPRESS_DB_PASSWORD", plan["configured_keys"])
        self.assertTrue(plan["remove_sandbox_data"])

    def test_remove_config_backs_up_service_settings_and_preserves_global_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            (config / "core.env").parent.mkdir(parents=True)
            core = config / "core.env"
            core.write_text("STACK_DOMAIN=example.test\n")
            service_config = root / "services" / "hermes" / ".env"
            service_config.parent.mkdir(parents=True, exist_ok=True)
            service_config.write_text(
                "HERMES_SUBDOMAIN=agent\nHERMES_DASHBOARD_PASSWORD=secret\n"
            )
            with mock.patch.object(remove, "ROOT", root), \
                 mock.patch.object(remove, "SERVICE_CONFIG", service_config):
                remove.remove_service_config()

            self.assertIn("STACK_DOMAIN=example.test", core.read_text())
            self.assertFalse(service_config.exists())
            backups = list(
                (root / "backups" / "config" / "services" / "hermes").glob(".env.*.bak")
            )
            self.assertEqual(len(backups), 1)
            self.assertIn("HERMES_DASHBOARD_PASSWORD=secret", backups[0].read_text())

    def test_confirmed_hermes_removal_wipes_only_declared_local_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = root / "services" / "hermes"
            service.mkdir(parents=True)
            sandbox = service / "data" / "sandboxes"
            sandbox.mkdir(parents=True)
            (sandbox / "workspace").write_text("user sandbox file")
            plan = {
                "domains": FakeDomains([]), "routes": [], "compose_ids": ["compose-id"],
                "sandbox_containers": [{"id": "task-id", "name": "hermes-task"}],
                "volumes": ["hermes_hermes_data"],
                "images": ["nousresearch/hermes-agent:v1", "nousresearch/hermes-sandbox:desktop"],
                "configured_keys": ["HERMES_SUBDOMAIN"],
                "remove_sandbox_data": True, "remove_service_config": True,
            }
            service_config = service / ".env"
            service_config.parent.mkdir(parents=True, exist_ok=True)
            service_config.write_text("HERMES_SUBDOMAIN=agent\n")
            core = root / "config" / "core.env"
            core.parent.mkdir(parents=True, exist_ok=True)
            core.write_text("STACK_DOMAIN=example.test\n")
            with mock.patch.object(remove, "ROOT", root), \
                 mock.patch.object(remove, "SERVICE_CONFIG", service_config), \
                 mock.patch.object(remove, "initialize") as initialize, \
                 mock.patch.object(remove, "SANDBOX_DATA", sandbox), \
                 mock.patch.object(remove, "compose_prefix", return_value=["docker", "compose"]), \
                 mock.patch.object(remove, "remove_routes") as remove_routes, \
                 mock.patch.object(remove, "run_command", return_value=FakeResult()) as run:
                remove.remove_hermes(plan)
                initialize.assert_called_once_with()

            calls = [call.args[0] for call in run.call_args_list]
            self.assertIn(["docker", "compose", "down", "--volumes", "--remove-orphans"], calls)
            self.assertIn(["docker", "rm", "-f", "task-id"], calls)
            self.assertIn(["docker", "image", "rm", "nousresearch/hermes-agent:v1"], calls)
            self.assertTrue(all("--force" not in call for call in calls))
            remove_routes.assert_called_once_with(plan)
            self.assertFalse(sandbox.exists())
            self.assertFalse(service_config.exists())
            self.assertEqual(core.read_text(), "STACK_DOMAIN=example.test\n")

    def test_route_removal_preserves_other_service_routes(self):
        routes = [
            {"hostname": "agent.example.test", "type": "docker", "target": "hermes"},
            {"hostname": "blog.example.test", "type": "docker", "target": "wordpress"},
        ]
        fake_domains = FakeDomains(routes)
        with tempfile.TemporaryDirectory() as temp:
            fake_domains.DOMAINS_FILE = Path(temp) / "domains.conf"
            fake_domains.DOMAINS_FILE.write_text("fixture\n")
            plan = {"domains": fake_domains, "routes": [routes[0]]}
            with mock.patch.object(remove, "CONFIG", Path(temp) / "config"), \
                 mock.patch.object(remove, "run_command", return_value=FakeResult("")) as run:
                remove.remove_routes(plan)

        self.assertEqual(fake_domains.saved, [routes[1]])
        self.assertEqual(fake_domains.rendered, [routes[1]])
        self.assertTrue(any("publish-cloudflare.py" in str(arg)
                            for arg in run.call_args_list[0].args[0]))

    def test_dry_run_and_noninteractive_invocations_never_remove(self):
        plan = {"routes": [], "compose_ids": [], "sandbox_containers": [], "volumes": [],
                "images": [], "configured_keys": [], "remove_sandbox_data": False,
                "remove_service_config": False}
        with mock.patch.object(remove, "build_plan", return_value=plan), \
             mock.patch.object(remove, "remove_hermes") as remove_action, \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.main(["hermes", "--dry-run"]), 0)
            remove_action.assert_not_called()

        with mock.patch.object(remove, "build_plan", return_value=plan), \
             mock.patch.object(remove, "remove_hermes") as remove_action, \
             mock.patch.object(remove.sys, "stdin", mock.Mock(isatty=mock.Mock(return_value=False))), \
             mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(remove.main(["hermes"]), 1)
            remove_action.assert_not_called()

    def test_wrong_confirmation_cancels_without_removal(self):
        plan = {"routes": [], "compose_ids": [], "sandbox_containers": [], "volumes": [],
                "images": [], "configured_keys": [], "remove_sandbox_data": False,
                "remove_service_config": False}
        with mock.patch.object(remove, "build_plan", return_value=plan), \
             mock.patch.object(remove, "remove_hermes") as remove_action, \
             mock.patch.object(remove.sys, "stdin", mock.Mock(isatty=mock.Mock(return_value=True))), \
             mock.patch("builtins.input", return_value="yes"), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(remove.main(["hermes"]), 0)
            remove_action.assert_not_called()

    def test_unsupported_service_fails_closed(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(remove.main(["wordpress"]), 2)


if __name__ == "__main__":
    unittest.main()
