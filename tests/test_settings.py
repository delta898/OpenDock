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
        self.assertEqual(settings.owner_path("MARIADB_VERSION"), Path("config/infra.env"))
        self.assertEqual(settings.owner_path("CADDY_VERSION"), Path("config/gateway.env"))
        self.assertEqual(settings.owner_path("SMTP_PASSWORD"), Path("config/shared/mail.env"))
        self.assertEqual(
            settings.owner_path("MARIADB_CLIENT_VERSION"),
            Path("config/shared/database.env"),
        )
        self.assertEqual(
            settings.owner_path("WORDPRESS_DB_PASSWORD"),
            Path("services/wordpress/.env"),
        )
        self.assertEqual(settings.owner_path("HERMES_VERSION"), Path("services/hermes/.env"))
        with self.assertRaises(ValueError):
            settings.owner_path("UNREGISTERED_SETTING")

    def test_every_defaults_key_matches_its_registered_owner(self):
        examples = sorted((ROOT / "config").rglob("*.env.default"))
        examples += sorted((ROOT / "services").glob("*/.env.default"))
        self.assertGreater(len(examples), 10)
        for example in examples:
            relative = example.relative_to(ROOT).as_posix()
            expected = relative.removesuffix(".default")
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
            (root / "services" / "wordpress").mkdir(parents=True)
            (root / "services" / "wordpress" / ".env.default").write_text(
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
                root / "services" / "wordpress" / ".env.default": "WORDPRESS_SUBDOMAIN=blog\n",
                root / "services" / "wordpress" / ".env": "WORDPRESS_SUBDOMAIN=wp\n",
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

    def test_compose_receives_base_shared_and_selected_service_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            service_local = root / "services" / "wordpress" / ".env"
            service_local.parent.mkdir(parents=True)
            service_local.write_text("WORDPRESS_VERSION=1\n")
            paths = [
                config / "core.env.default", config / "infra.env.default",
                config / "shared" / "mail.env.default",
                config / "shared" / "database.env.default",
                root / "services" / "wordpress" / ".env.default",
                config / "core.env", config / "infra.env",
                config / "shared" / "mail.env",
                config / "shared" / "database.env",
                service_local,
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                result = settings.compose_env_files("wordpress")
            self.assertEqual(result, paths)

    def test_hermes_compose_defaults_precede_private_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            hermes = root / "services" / "hermes"
            paths = [
                config / "core.env.default", config / "infra.env.default",
                config / "shared" / "mail.env.default",
                config / "shared" / "database.env.default", hermes / ".env.default",
                config / "core.env", config / "infra.env",
                config / "shared" / "mail.env", config / "shared" / "database.env",
                hermes / ".env",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                result = settings.compose_env_files("hermes")
            self.assertEqual(result, paths)

    def test_gateway_uses_gateway_owned_defaults_and_local_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            paths = [
                config / "core.env.default", config / "infra.env.default",
                config / "gateway.env.default", config / "shared" / "mail.env.default",
                config / "shared" / "database.env.default", config / "core.env",
                config / "infra.env", config / "gateway.env",
                config / "shared" / "mail.env", config / "shared" / "database.env",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                self.assertEqual(settings.compose_env_files("gateway"), paths)

    def test_current_gateway_override_wins_over_legacy_gateway_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            files = {
                config / "gateway.env.default": "CADDY_VERSION=2\n",
                root / "gateway" / ".env": "CADDY_VERSION=1\n",
                config / "gateway.env": "CADDY_VERSION=custom\n",
            }
            for path, contents in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                values = settings.load_values(service="gateway", process_env=False)
            self.assertEqual(values["CADDY_VERSION"], "custom")

    def test_legacy_gateway_env_migrates_custom_port_and_drops_tracked_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            old_file = root / "gateway" / ".env"
            old_file.parent.mkdir(parents=True)
            old_file.write_text(
                "CADDY_VERSION=2\nHTTP_PORT=8080\nHTTPS_PORT=443\n"
            )
            (config / "gateway.env.default").parent.mkdir(parents=True)
            (config / "gateway.env.default").write_text(
                "CADDY_VERSION=2\nHTTP_PORT=80\nHTTPS_PORT=443\n"
            )
            legacy = config / "migrations" / "gateway-env-v1.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                '{"CADDY_VERSION":"2","HTTP_PORT":"80","HTTPS_PORT":"443"}\n'
            )
            backups = root / "backups" / "config"
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "BACKUPS", backups):
                settings.migrate_legacy_gateway_defaults()

            self.assertFalse(old_file.exists())
            self.assertEqual(
                settings.parse_env(config / "gateway.env"), {"HTTP_PORT": "8080"}
            )
            backup = next((backups / "legacy-gateway").glob("*.bak"))
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

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

    def test_legacy_service_config_migrates_to_private_service_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            old_service_config = config / "services" / "wordpress.env"
            old_service_config.parent.mkdir(parents=True)
            old_service_config.write_text(
                "WORDPRESS_DB_PASSWORD=legacy-wp-secret\n"
                "WORDPRESS_SUBDOMAIN=old-blog\n"
            )
            local = root / "services" / "wordpress" / ".env"
            local.parent.mkdir(parents=True)
            local.write_text("WORDPRESS_SUBDOMAIN=new-blog\n")
            backups = root / "backups" / "config"
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "BACKUPS", backups), \
                 mock.patch.object(settings, "LEGACY_ENV", root / "missing-common.env"):
                settings.initialize()

            self.assertFalse(old_service_config.exists())
            migrated = settings.parse_env(local)
            self.assertEqual(migrated["WORDPRESS_DB_PASSWORD"], "legacy-wp-secret")
            self.assertEqual(migrated["WORDPRESS_SUBDOMAIN"], "new-blog")
            saved = list((backups / "legacy-services").glob("wordpress.*.bak"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)

    def test_legacy_tracked_service_defaults_are_pruned_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            service = root / "services" / "wordpress"
            service.mkdir(parents=True)
            default = service / ".env.default"
            default.write_text(
                "WORDPRESS_VERSION=7-php8.3-apache\n"
                "WORDPRESS_CONTAINER_NAME=wordpress\n"
            )
            local = service / ".env"
            local.write_text(
                "WORDPRESS_VERSION=7-php8.3-apache\n"
                "WORDPRESS_CONTAINER_NAME=my-wordpress\n"
            )
            backups = root / "backups" / "config"
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "BACKUPS", backups):
                settings.migrate_legacy_service_defaults()
                migrated = settings.parse_env(local)
                local.write_text("WORDPRESS_VERSION=7-php8.3-apache\n")
                settings.migrate_legacy_service_defaults()

            self.assertEqual(migrated, {"WORDPRESS_CONTAINER_NAME": "my-wordpress"})
            self.assertEqual(settings.parse_env(local)["WORDPRESS_VERSION"], "7-php8.3-apache")
            self.assertEqual(len(list((backups / "legacy-service-defaults").glob("*.bak"))), 1)
            backup = next((backups / "legacy-service-defaults").glob("*.bak"))
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            marker = config / ".service-default-migration-v1"
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_legacy_default_is_pruned_even_after_renovate_changed_the_template(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            service = root / "services" / "wordpress"
            service.mkdir(parents=True)
            (service / ".env.default").write_text(
                "WORDPRESS_VERSION=8-php8.3-apache\n"
            )
            local = service / ".env"
            local.write_text(
                "WORDPRESS_VERSION=7-php8.3-apache\n"
                "WORDPRESS_CONTAINER_NAME=my-wordpress\n"
            )
            migration = config / "migrations" / "service-env-v1.json"
            migration.parent.mkdir(parents=True)
            migration.write_text(
                '{"wordpress":{"WORDPRESS_VERSION":"7-php8.3-apache"}}\n'
            )
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "BACKUPS", root / "backups" / "config"):
                settings.migrate_legacy_service_defaults()

            self.assertEqual(
                settings.parse_env(local),
                {"WORDPRESS_CONTAINER_NAME": "my-wordpress"},
            )

    def test_legacy_infra_env_migrates_custom_values_and_removes_old_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config"
            old_file = root / "infra" / ".env"
            old_file.parent.mkdir(parents=True)
            old_file.write_text(
                "MARIADB_VERSION=11.8-noble\n"
                "POSTGRES_VERSION=17-alpine\n"
                "REDIS_VERSION=8-alpine\n"
            )
            (config / "infra.env.default").parent.mkdir(parents=True)
            (config / "infra.env.default").write_text(
                "MARIADB_VERSION=11.8-noble\n"
                "POSTGRES_VERSION=18-bookworm\n"
                "REDIS_VERSION=8-alpine\n"
            )
            legacy = config / "migrations" / "infra-env-v1.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                '{"MARIADB_VERSION":"11.8-noble",'
                '"POSTGRES_VERSION":"18-bookworm",'
                '"REDIS_VERSION":"8-alpine"}\n'
            )
            backups = root / "backups" / "config"
            with mock.patch.object(settings, "ROOT", root), \
                 mock.patch.object(settings, "CONFIG", config), \
                 mock.patch.object(settings, "BACKUPS", backups):
                settings.migrate_legacy_infra_defaults()

            self.assertFalse(old_file.exists())
            self.assertEqual(
                settings.parse_env(config / "infra.env"),
                {"POSTGRES_VERSION": "17-alpine"},
            )
            backup = next((backups / "legacy-infra").glob("*.bak"))
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

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
