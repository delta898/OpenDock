"""Tests for optional per-service lifecycle message declarations."""

from pathlib import Path
import sys
import tempfile
import unittest
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from opendock_capabilities import ComposeOperations, ServiceContext, post_start
from opendock_catalog import CatalogError, ServiceCatalog, ServiceDefinition


class LifecycleContractTests(unittest.TestCase):
    def service_context(self, name, directory, capabilities):
        descriptor = {
            "service_id": name,
            "capability_api_version": 1,
            "capabilities": capabilities,
        }
        service = ServiceDefinition(
            name=name,
            directory=directory,
            compose_file=directory / "compose.yml",
            descriptor_file=directory / "opendock.toml",
            descriptor=MappingProxyType(descriptor),
        )
        return ServiceContext(
            service=service,
            settings=MappingProxyType({}),
            compose=ComposeOperations(lambda *_args, **_kwargs: None, lambda _name: False),
            report=lambda _message: None,
        )

    def test_post_start_calls_only_declared_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            new_action = root / "new-action"
            new_action.mkdir()
            (new_action / "opendock.py").write_text(
                "OPENDOCK_CAPABILITY_API_VERSION = 1\n"
                "def post_start(context): return None\n"
            )
            post_start(self.service_context("new-action", new_action, ["post_start"]))
            post_start(self.service_context("no-action", root, []))

    def catalog_with_descriptor(self, descriptor):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        service = root / "services/extensions/example-service/releases/1.0.0"
        service.mkdir(parents=True)
        (service / "compose.yml").write_text("services: {}\n")
        (service / "opendock.toml").write_text(descriptor)
        registry = root / "services/extensions/installed.toml"
        registry.write_text(
            'schema_version = 1\n\n'
            '[[extensions]]\n'
            'service_id = "example-service"\n'
            'version = "1.0.0"\n'
            'release_path = "services/extensions/example-service/releases/1.0.0"\n'
            f'sha256 = "{"a" * 64}"\n'
            'installed_at = "test"\n'
        )
        return temporary, root

    def test_lifecycle_messages_are_optional_and_discovered(self):
        temporary, root = self.catalog_with_descriptor(
            'schema_version = 1\n'
            'service_id = "example-service"\n'
            'version = "1.0.0"\n'
            'capabilities = []\n'
            'dependencies = []\n\n'
            '[lifecycle.messages]\n'
            'pre_start = "Startup can take a while."\n'
            'post_launch = "Refresh the page if setup is not ready."\n'
        )
        self.addCleanup(temporary.cleanup)

        service = ServiceCatalog(root).get("example-service")

        self.assertEqual(service.lifecycle_messages["pre_start"], "Startup can take a while.")
        self.assertEqual(
            service.lifecycle_messages["post_launch"],
            "Refresh the page if setup is not ready.",
        )

        without_messages, empty_root = self.catalog_with_descriptor(
            'schema_version = 1\n'
            'service_id = "example-service"\n'
            'version = "1.0.0"\n'
            'capabilities = []\n'
            'dependencies = []\n'
        )
        self.addCleanup(without_messages.cleanup)
        self.assertEqual(ServiceCatalog(empty_root).get("example-service").lifecycle_messages, {})

    def test_post_launch_is_not_an_action_capability_name(self):
        temporary, root = self.catalog_with_descriptor(
            'schema_version = 1\n'
            'service_id = "example-service"\n'
            'version = "1.0.0"\n'
            'capability_api_version = 1\n'
            'capabilities = ["post_launch"]\n'
            'dependencies = []\n'
        )
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(CatalogError, "unsupported capabilities: post_launch"):
            ServiceCatalog(root)

    def test_lifecycle_messages_reject_unknown_stages_and_control_codes(self):
        for message_table in (
            '[lifecycle.messages]\nafter_purge = "unsupported"\n',
            '[lifecycle.messages]\npre_start = "unsafe\\u001b"\n',
            '[lifecycle.messages]\npost_launch = "  "\n',
        ):
            with self.subTest(message_table=message_table):
                temporary, root = self.catalog_with_descriptor(
                    'schema_version = 1\n'
                    'service_id = "example-service"\n'
                    'version = "1.0.0"\n'
                    'capabilities = []\n'
                    'dependencies = []\n\n'
                    + message_table
                )
                self.addCleanup(temporary.cleanup)
                with self.assertRaises(CatalogError):
                    ServiceCatalog(root)


if __name__ == "__main__":
    unittest.main()
