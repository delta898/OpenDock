"""Tests for static catalog validation and package extraction safety."""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from opendock_distribution import DistributionError, _safe_extract, validate_catalog


class DistributionTests(unittest.TestCase):
    def catalog(self, **release_overrides):
        release = {
            "version": "1.0.0",
            "artifact": "packages/example-service/1.0.0/opendock-service.zip",
            "sha256": "a" * 64,
            "size_bytes": 12,
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

if __name__ == "__main__":
    unittest.main()
