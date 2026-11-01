"""Tests for configuration ownership, migration, and Compose file ordering."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "opendock_settings", ROOT / "scripts" / "opendock_settings.py"
)
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class SettingsTests(unittest.TestCase):
    def test_key_ownership_is_explicit(self):
        self.assertEqual(settings.owner_path("STACK_DOMAIN"), Path("config/core.env"))
        self.assertEqual(settings.owner_path("POSTGRES_ADMIN_PASSWORD"), Path("config/infra.env"))
        self.assertEqual(settings.owner_path("SMTP_PASSWORD"), Path("config/shared/mail.env"))
        self.assertEqual(
            settings.owner_path("WORDPRESS_DB_PASSWORD"),
            Path("config/services/wordpress.env"),
        )
        self.assertEqual(settings.owner_path("HERMES_VERSION"), Path("services/hermes/.env"))
        with self.assertRaises(ValueError):
            settings.owner_path("UNREGISTERED_SETTING")

    def test_every_defaults_key_matches_its_registered_owner(self):
        examples = sorted((ROOT / "config").rglob("*.env.default"))
        examples += sorted((ROOT / "config").rglob("*.env.example"))
        examples.append(ROOT / "services/hermes/.env.default")
        self.assertGreater(len(examples), 10)
        for example in examples:
            relative = example.relative_to(ROOT).as_posix()
            suffix = ".default" if relative.endswith(".env.default") else ".example"
            expected = relative.removesuffix(suffix)
            for key in settings.parse_env(example):
                actual = settings.owner_path(key).as_posix()
                self.assertEqual(actual, expected, f"{key} is in the wrong config template")

    def test_legacy_file_migrates_and_is_backed_up_without_printing_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            legacy = root / "common.env"
            backups = root / "backups" / "config"
            (config / "core.env.default").parent.mkdir(parents=True)
            (config / "core.env.default").write_text("STACK_DOMAIN=example.com\n")
            (config / "infra.env.default").write_text("POSTGRES_ADMIN_PASSWORD=change-me\n")
            (config / "shared" / "mail.env.default").parent.mkdir(parents=True)
            (config / "shared" / "mail.env.default").write_text("SMTP_HOST=\n")
            (config / "services" / "wordpress.env.example").parent.mkdir(parents=True)
            (config / "services" / "wordpress.env.example").write_text(
                "WORDPRESS_DB_PASSWORD=change-me\n"
            )
            legacy.write_text(
                "STACK_DOMAIN=example.test\nPOSTGRES_ADMIN_PASSWORD=db-secret\n"
                "SMTP_HOST=mail.example.test\nWORDPRESS_DB_PASSWORD=wp-secret\n"
                "HERMES_DASHBOARD_SECRET=hermes-secret\n"
            )
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", legacy), \
                 mock.patch.object(settings, "BACKUPS", backups):
                settings.initialize()
                merged = settings.load_values(process_env=False, legacy=False)

            self.assertFalse(legacy.exists())
            self.assertEqual(merged["STACK_DOMAIN"], "example.test")
            self.assertEqual(merged["POSTGRES_ADMIN_PASSWORD"], "db-secret")
            self.assertEqual(merged["SMTP_HOST"], "mail.example.test")
            self.assertEqual(merged["WORDPRESS_DB_PASSWORD"], "wp-secret")
            self.assertEqual(merged["HERMES_DASHBOARD_SECRET"], "hermes-secret")
            self.assertEqual(
                settings.parse_env(root / "services/hermes/.env")["HERMES_DASHBOARD_SECRET"],
                "hermes-secret",
            )
            saved = list(backups.glob("common.env.*.bak"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)

    def test_unknown_legacy_key_stops_before_legacy_file_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            legacy = root / "common.env"
            legacy.write_text("UNREGISTERED_SETTING=keep-me\n")
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", legacy), \
                 mock.patch.object(settings, "BACKUPS", root / "backups" / "config"):
                with self.assertRaises(ValueError):
                    settings.initialize()
            self.assertEqual(legacy.read_text(), "UNREGISTERED_SETTING=keep-me\n")

    def test_split_values_override_examples_in_owner_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            files = {
                config / "core.env.default": "STACK_DOMAIN=example.com\n",
                config / "core.env": "STACK_DOMAIN=core.test\n",
                config / "infra.env.default": "POSTGRES_ADMIN_USER=default\n",
                config / "infra.env": "POSTGRES_ADMIN_USER=infra\n",
                config / "shared" / "mail.env.default": "SMTP_PORT=587\n",
                config / "shared" / "mail.env": "SMTP_PORT=2525\n",
                config / "services" / "wordpress.env.example": "WORDPRESS_SUBDOMAIN=blog\n",
                config / "services" / "wordpress.env": "WORDPRESS_SUBDOMAIN=wp\n",
            }
            for path, contents in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                values = settings.load_values(service="wordpress", process_env=False)
            self.assertEqual(values["STACK_DOMAIN"], "core.test")
            self.assertEqual(values["POSTGRES_ADMIN_USER"], "infra")
            self.assertEqual(values["SMTP_PORT"], "2525")
            self.assertEqual(values["WORDPRESS_SUBDOMAIN"], "wp")

    def test_compose_receives_only_base_and_selected_service_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            service_local = root / "services" / "wordpress" / ".env"
            service_local.parent.mkdir(parents=True)
            service_local.write_text("WORDPRESS_VERSION=1\n")
            paths = [
                config / "core.env.default", config / "core.env",
                config / "infra.env.default", config / "infra.env",
                config / "shared" / "mail.env.default", config / "shared" / "mail.env",
                config / "services" / "wordpress.env.example",
                config / "services" / "wordpress.env",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                result = settings.compose_env_files("wordpress")
            self.assertEqual(result, paths[:8] + [service_local])

    def test_hermes_compose_defaults_precede_private_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            hermes = root / "services" / "hermes"
            paths = [
                config / "core.env.default", config / "core.env",
                config / "infra.env.default", config / "infra.env",
                config / "shared" / "mail.env.default", config / "shared" / "mail.env",
                hermes / ".env.default", hermes / ".env",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                result = settings.compose_env_files("hermes")
            self.assertEqual(result, paths)

    def test_hermes_setup_values_use_service_default_and_local_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            hermes = root / "services" / "hermes"
            files = {
                config / "core.env.default": "STACK_DOMAIN=example.com\n",
                hermes / ".env.default": "HERMES_SUBDOMAIN=hermes\nHERMES_VERSION=v1\n",
                hermes / ".env": "HERMES_VERSION=v2\n",
            }
            for path, contents in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                defaults = settings.load_values(service="hermes", examples=True)
                values = settings.load_values(service="hermes", process_env=False)
            self.assertEqual(defaults["HERMES_VERSION"], "v1")
            self.assertEqual(values["HERMES_SUBDOMAIN"], "hermes")
            self.assertEqual(values["HERMES_VERSION"], "v2")

    def test_updates_are_backed_up_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            path = config / "core.env"
            path.parent.mkdir(parents=True)
            path.write_text("STACK_DOMAIN=old.test\n")
            backups = root / "backups" / "config"
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "BACKUPS", backups):
                changed = settings.write_values({"STACK_DOMAIN": "new.test"})
            self.assertEqual(changed, ["STACK_DOMAIN"])
            self.assertEqual(settings.parse_env(path)["STACK_DOMAIN"], "new.test")
            saved = list(backups.glob("core.env.*.bak"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)

    def test_hermes_setup_writes_only_the_private_service_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default = root / "services" / "hermes" / ".env.default"
            default.parent.mkdir(parents=True)
            default.write_text("HERMES_DASHBOARD_PASSWORD=change-me\n")
            backups = root / "backups" / "config"
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "BACKUPS", backups):
                changed = settings.write_values({"HERMES_DASHBOARD_PASSWORD": "generated-secret"})
            self.assertEqual(changed, ["HERMES_DASHBOARD_PASSWORD"])
            self.assertEqual(
                settings.parse_env(default)["HERMES_DASHBOARD_PASSWORD"], "change-me"
            )
            self.assertEqual(
                settings.parse_env(root / "services/hermes/.env")["HERMES_DASHBOARD_PASSWORD"],
                "generated-secret",
            )
            self.assertEqual(
                (root / "services/hermes/.env").stat().st_mode & 0o777, 0o600
            )


if __name__ == "__main__":
    unittest.main()
