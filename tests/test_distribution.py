"""Tests for static catalog validation and package extraction safety."""

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from opendock_distribution import (
    DistributionError,
    _safe_extract,
    install_local_file,
    load_cached,
    mark_setup_complete,
    validate_catalog,
)


class DistributionTests(unittest.TestCase):
    def catalog(self, **release_overrides):
        release = {
            "version": "1.0.0",
            "artifact": "packages/example-service/1.0.0/opendock-service.zip",
            "sha256": "a" * 64,
            "size_bytes": 12,
            "descriptor_schema": {"min": 1, "max": 1},
            "capability_api": {"min": 1, "max": 1},
            "opendock": {"min": "0.1.0", "max": None},
            "supported_hosts": ["linux"],
            **release_overrides,
        }
        return {
            "catalog_schema_version": 1,
            "catalog_revision": "test",
            "services": [{
                "service_id": "example-service",
                "display_name": "Example Service",
                "summary": "Monitoring",
                "tags": ["monitoring"],
                "releases": [release],
            }],
        }

    def test_accepts_catalog_with_service_scoped_artifact(self):
        catalog = validate_catalog(json.dumps(self.catalog()).encode())
        self.assertEqual(catalog["services"][0]["service_id"], "example-service")

    def test_catalog_accepts_compact_primary_image_and_rejects_full_path(self):
        catalog = self.catalog()
        catalog["services"][0]["primary_image"] = "n8n:2.46.6"
        validate_catalog(json.dumps(catalog).encode())
        catalog["services"][0]["primary_image"] = "docker.example/n8n:2.46.6"
        with self.assertRaises(DistributionError):
            validate_catalog(json.dumps(catalog).encode())

    def test_rejects_artifact_path_escape(self):
        raw = json.dumps(self.catalog(artifact="packages/example-service/../../evil.zip")).encode()
        with self.assertRaises(DistributionError):
            validate_catalog(raw)

    def test_rejects_duplicate_zip_members(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("compose.yml", "services: {}")
            archive.writestr("compose.yml", "overwritten")
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(DistributionError):
                    _safe_extract(archive, Path(directory))

    def test_rejects_zip_path_traversal(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../outside", "data")
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(DistributionError):
                    _safe_extract(archive, Path(directory))

    def test_safe_extract_preserves_executable_bit_with_normalized_permissions(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            executable = zipfile.ZipInfo("commands/multisite")
            executable.external_attr = (0o100777 << 16)
            archive.writestr(executable, "#!/bin/sh\nexit 0\n")
            regular = zipfile.ZipInfo("README.md")
            regular.external_attr = (0o100666 << 16)
            archive.writestr(regular, "WordPress integration\n")
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _safe_extract(archive, root)
                self.assertEqual(
                    (root / "commands/multisite").stat().st_mode & 0o777,
                    0o755,
                )
                self.assertEqual(
                    (root / "README.md").stat().st_mode & 0o777,
                    0o644,
                )

    def test_local_package_install_uses_safe_extraction_without_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "example-service.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(
                    "opendock.toml",
                    'schema_version = 1\nservice_id = "example-service"\n'
                    'version = "0.1.0-local.1"\ndisplay_name = "Example Service"\n'
                    'capabilities = []\ndependencies = []\n',
                )
                archive.writestr("compose.yml", "services: {}\n")
                command = zipfile.ZipInfo("commands/example")
                command.external_attr = 0o100755 << 16
                archive.writestr(command, "#!/bin/sh\nexit 0\n")

            class EmptyPlatform:
                components = ()

            with patch("opendock_catalog.PlatformCatalog", return_value=EmptyPlatform()):
                destination = install_local_file(package, root)

            self.assertEqual(
                destination,
                root / "services/extensions/example-service/releases/0.1.0-local.1",
            )
            self.assertTrue((destination / "commands/example").stat().st_mode & 0o111)
            registry = root / "services/extensions/installed.toml"
            self.assertIn('service_id = "example-service"', registry.read_text())

    def test_first_service_setup_completion_is_persisted_in_installed_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "example-service.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(
                    "opendock.toml",
                    'schema_version = 1\nservice_id = "example-service"\n'
                    'version = "0.1.0-local.1"\ncapabilities = []\ndependencies = []\n',
                )
                archive.writestr("compose.yml", "services: {}\n")

            class EmptyPlatform:
                components = ()

            with patch("opendock_catalog.PlatformCatalog", return_value=EmptyPlatform()):
                install_local_file(package, root)
                from opendock_catalog import ServiceCatalog
                self.assertFalse(ServiceCatalog(root).get("example-service").setup_complete)
                mark_setup_complete(root, ["example-service"])
                self.assertTrue(ServiceCatalog(root).get("example-service").setup_complete)

            registry = root / "services/extensions/installed.toml"
            self.assertEqual(registry.stat().st_mode & 0o777, 0o600)
            self.assertIn("setup_completed_at =", registry.read_text())

    def test_reinstall_keeps_completed_service_setup_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            class EmptyPlatform:
                components = ()

            def package(version):
                path = root / f"example-service-{version}.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(
                        "opendock.toml",
                        'schema_version = 1\nservice_id = "example-service"\n'
                        f'version = "{version}"\ncapabilities = []\ndependencies = []\n',
                    )
                    archive.writestr("compose.yml", "services: {}\n")
                return path

            with patch("opendock_catalog.PlatformCatalog", return_value=EmptyPlatform()):
                install_local_file(package("0.1.0-local.1"), root)
                mark_setup_complete(root, ["example-service"])
                install_local_file(package("0.1.0-local.2"), root)
                from opendock_catalog import ServiceCatalog
                service = ServiceCatalog(root).get("example-service")

        self.assertTrue(service.setup_complete)
        self.assertEqual(service.descriptor["version"], "0.1.0-local.2")

    def test_search_cache_refreshes_when_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "catalog.json"
            with patch("opendock_distribution.cache_path", return_value=cache), patch(
                "opendock_distribution.fetch_catalog",
                return_value=(self.catalog(), cache),
            ) as fetch:
                result = load_cached("dev")
        self.assertEqual(result["services"][0]["service_id"], "example-service")
        fetch.assert_called_once_with("dev")

    def test_search_cache_refreshes_when_older_than_24_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "catalog.json"
            cache.write_text(json.dumps(self.catalog()))
            old = 1
            os.utime(cache, (old, old))
            with patch("opendock_distribution.cache_path", return_value=cache), patch(
                "opendock_distribution.fetch_catalog",
                return_value=(self.catalog(), cache),
            ) as fetch:
                load_cached("dev")
        fetch.assert_called_once_with("dev")

    def test_search_uses_fresh_cache_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "catalog.json"
            cache.write_text(json.dumps(self.catalog()))
            with patch("opendock_distribution.cache_path", return_value=cache), patch(
                "opendock_distribution.fetch_catalog"
            ) as fetch:
                result = load_cached("dev")
        self.assertEqual(result["services"][0]["service_id"], "example-service")
        fetch.assert_not_called()

    def test_search_repairs_invalid_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "catalog.json"
            cache.write_text("not json")
            with patch("opendock_distribution.cache_path", return_value=cache), patch(
                "opendock_distribution.fetch_catalog",
                return_value=(self.catalog(), cache),
            ) as fetch:
                load_cached("dev")
        fetch.assert_called_once_with("dev")

if __name__ == "__main__":
    unittest.main()
