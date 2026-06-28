#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
COMMON_ENV = ROOT_DIR / "common.env"
COMMON_ENV_EXAMPLE = ROOT_DIR / "common.env.example"
WORDPRESS_DIR = ROOT_DIR / "services" / "wordpress"
WORDPRESS_ENV = WORDPRESS_DIR / ".env"
WEBROOT = WORDPRESS_DIR / "data" / "webroot"
BACKUP_DIR = WORDPRESS_DIR / "backups"
CONTAINER_WEBROOT = "/var/www/html"

CONFIG_BEGIN = "/* BEGIN OpenDock WordPress multisite */"
CONFIG_END = "/* END OpenDock WordPress multisite */"
HTTPS_BEGIN = "/* BEGIN OpenDock reverse proxy HTTPS */"
HTTPS_END = "/* END OpenDock reverse proxy HTTPS */"
HTACCESS_BEGIN = "# BEGIN WordPress"
HTACCESS_END = "# END WordPress"
MULTISITE_CONSTANTS = (
    "WP_ALLOW_MULTISITE",
    "MULTISITE",
    "SUBDOMAIN_INSTALL",
    "DOMAIN_CURRENT_SITE",
    "PATH_CURRENT_SITE",
    "SITE_ID_CURRENT_SITE",
    "BLOG_ID_CURRENT_SITE",
)


def parse_env_file(path):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        values[key] = value

    return values


def load_env():
    if not COMMON_ENV.exists():
        raise SystemExit(
            "Missing required file: common.env\n\n"
            "To continue:\n"
            "  cp common.env.example common.env\n"
            "  nano common.env\n"
            "  make check-config"
        )

    env = {}
    env.update(parse_env_file(COMMON_ENV_EXAMPLE))
    env.update(parse_env_file(COMMON_ENV))
    env.update(parse_env_file(WORDPRESS_ENV))
    env.update(os.environ)
    return env


def require_env(env, names):
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise SystemExit(f"Missing required values: {' '.join(missing)}")


def wordpress_hostname(env):
    subdomain = env.get("WORDPRESS_SUBDOMAIN", "blog").strip()
    domain = env.get("STACK_DOMAIN", "").strip()
    if not domain:
        raise SystemExit("Missing STACK_DOMAIN in common.env")
    if domain == "example.com":
        raise SystemExit("Refusing to enable multisite with STACK_DOMAIN=example.com")
    return f"{subdomain}.{domain}" if subdomain else domain


def confirm(args, hostname):
    if args.yes:
        return

    print("This will convert WordPress into subdirectory multisite mode.")
    print()
    print("This changes WordPress configuration and database behavior.")
    print("Returning to single-site mode is not a simple toggle after you create sites or content.")
    print()
    print("OpenDock will create backups before making changes:")
    print(f"  {BACKUP_DIR}/wp-config.php.<timestamp>")
    print(f"  {BACKUP_DIR}/.htaccess.<timestamp>")
    print(f"  {BACKUP_DIR}/wordpress-multisite-<timestamp>.sql")
    print()
    print("Multisite URL style:")
    print(f"  https://{hostname}/site-name/")
    print()
    answer = input("Continue? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        raise SystemExit("Canceled.")


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def capture(command, **kwargs):
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )


def print_command_output(result):
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if output:
        print(output)


def container_running(name):
    try:
        result = capture(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    return result.stdout.strip() == "true"


def ensure_runtime(env):
    wordpress_container = env.get("WORDPRESS_CONTAINER_NAME", "wordpress")
    if not container_running(wordpress_container):
        raise SystemExit(
            f"WordPress container is not running: {wordpress_container}\n\n"
            "Start it first:\n"
            "  make launch wordpress"
        )

    if not container_running("mariadb"):
        raise SystemExit(
            "MariaDB container is not running: mariadb\n\n"
            "Start it first:\n"
            "  make up infra"
        )


def wordpress_container(env):
    return env.get("WORDPRESS_CONTAINER_NAME", "wordpress")


def container_path(name):
    return f"{CONTAINER_WEBROOT}/{name}"


def container_file_exists(container, name):
    return (
        subprocess.run(
            ["docker", "exec", container, "test", "-f", container_path(name)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def ensure_files(env):
    container = wordpress_container(env)
    if not container_file_exists(container, "wp-config.php"):
        raise SystemExit(
            f"Missing WordPress config: {container_path('wp-config.php')}\n\n"
            "Open the WordPress site once and complete the initial installation first."
        )


def ensure_htaccess(container):
    if not container_file_exists(container, ".htaccess"):
        run(["docker", "exec", container, "touch", container_path(".htaccess")])
        run(
            [
                "docker",
                "exec",
                container,
                "chown",
                "www-data:www-data",
                container_path(".htaccess"),
            ]
        )


def copy_from_container(container, name, destination):
    run(
        ["docker", "cp", f"{container}:{container_path(name)}", str(destination)],
        stdout=subprocess.DEVNULL,
    )


def copy_to_container(container, source, name):
    run(
        ["docker", "cp", str(source), f"{container}:{container_path(name)}"],
        stdout=subprocess.DEVNULL,
    )
    run(
        [
            "docker",
            "exec",
            container,
            "chown",
            "www-data:www-data",
            container_path(name),
        ]
    )


def backup_file(container, name, timestamp):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{name}.{timestamp}"
    copy_from_container(container, name, backup)
    print(f"  {backup}")
    return backup


def backup_database(env, timestamp):
    require_env(env, ["MARIADB_ROOT_PASSWORD", "WORDPRESS_DB_NAME"])
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"wordpress-multisite-{timestamp}.sql"

    command = [
        "docker",
        "exec",
        "-e",
        f"MYSQL_PWD={env['MARIADB_ROOT_PASSWORD']}",
        "mariadb",
        "mariadb-dump",
        "-u",
        "root",
        "--single-transaction",
        "--quick",
        env["WORDPRESS_DB_NAME"],
    ]

    try:
        with backup.open("w") as handle:
            subprocess.run(command, check=True, text=True, stdout=handle)
    except subprocess.CalledProcessError:
        backup.unlink(missing_ok=True)
        raise

    print(f"  {backup}")
    return backup


def replace_between_markers(text, start, end, replacement):
    start_index = text.find(start)
    end_index = text.find(end)

    if start_index != -1 and end_index != -1 and end_index > start_index:
        end_index += len(end)
        return text[:start_index] + replacement + text[end_index:]

    return None


def multisite_config_block(hostname):
    return f"""\
{CONFIG_BEGIN}
define( 'WP_ALLOW_MULTISITE', true );
define( 'MULTISITE', true );
define( 'SUBDOMAIN_INSTALL', false );
define( 'DOMAIN_CURRENT_SITE', '{hostname}' );
define( 'PATH_CURRENT_SITE', '/' );
define( 'SITE_ID_CURRENT_SITE', 1 );
define( 'BLOG_ID_CURRENT_SITE', 1 );
{CONFIG_END}
"""


def https_config_block():
    return f"""\
{HTTPS_BEGIN}
if (isset($_SERVER['HTTP_X_FORWARDED_PROTO']) && 'https' === $_SERVER['HTTP_X_FORWARDED_PROTO']) {{
    $_SERVER['HTTPS'] = 'on';
}}
{HTTPS_END}
"""


def has_multisite_config(path):
    text = path.read_text()
    return bool(
        re.search(r"define\s*\(\s*['\"]MULTISITE['\"]\s*,\s*true\s*\)", text)
    )


def remove_multisite_defines(text):
    for name in MULTISITE_CONSTANTS:
        pattern = (
            rf"^[ \t]*define\s*\(\s*['\"]{re.escape(name)}['\"]\s*,"
            rf".*?\)\s*;\s*(?:\r?\n)?"
        )
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    return text


def patch_wp_config(path, hostname):
    text = path.read_text()
    block = multisite_config_block(hostname)

    replaced = replace_between_markers(text, CONFIG_BEGIN, CONFIG_END, block)
    if replaced is not None:
        path.write_text(replaced)
        return "updated"

    text = remove_multisite_defines(text)

    marker = "/* That's all, stop editing!"
    if marker not in text:
        marker = "/* That's all, stop editing! Happy publishing. */"

    if marker in text:
        text = text.replace(marker, block + "\n" + marker, 1)
    else:
        text = text.rstrip() + "\n\n" + block

    path.write_text(text)
    return "enabled"


def patch_https_config(path):
    text = path.read_text()
    block = https_config_block()

    replaced = replace_between_markers(text, HTTPS_BEGIN, HTTPS_END, block)
    if replaced is not None:
        path.write_text(replaced)
        return "updated"

    marker = CONFIG_BEGIN
    if marker in text:
        text = text.replace(marker, block + "\n" + marker, 1)
    else:
        stop_marker = "/* That's all, stop editing!"
        if stop_marker not in text:
            stop_marker = "/* That's all, stop editing! Happy publishing. */"

        if stop_marker in text:
            text = text.replace(stop_marker, block + "\n" + stop_marker, 1)
        else:
            text = text.rstrip() + "\n\n" + block

    path.write_text(text)
    return "enabled"


def multisite_htaccess_block():
    return f"""\
{HTACCESS_BEGIN}
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule .* - [E=HTTP_AUTHORIZATION:%{{HTTP:Authorization}}]
RewriteBase /
RewriteRule ^index\\.php$ - [L]

# Add a trailing slash to /wp-admin.
RewriteRule ^wp-admin$ wp-admin/ [R=301,L]

RewriteCond %{{REQUEST_FILENAME}} -f [OR]
RewriteCond %{{REQUEST_FILENAME}} -d
RewriteRule ^ - [L]
RewriteRule ^(wp-(content|admin|includes).*) $1 [L]
RewriteRule ^(.*\\.php)$ $1 [L]
RewriteRule . index.php [L]
</IfModule>
{HTACCESS_END}
"""


def patch_htaccess(path):
    text = path.read_text()
    block = multisite_htaccess_block()

    replaced = replace_between_markers(text, HTACCESS_BEGIN, HTACCESS_END, block)
    if replaced is not None:
        path.write_text(replaced)
        return "updated"

    path.write_text(text.rstrip() + "\n\n" + block)
    return "enabled"


def wp_cli_convert(env, hostname):
    require_env(
        env,
        [
            "WORDPRESS_DB_HOST",
            "WORDPRESS_DB_NAME",
            "WORDPRESS_DB_USER",
            "WORDPRESS_DB_PASSWORD",
            "WORDPRESS_TABLE_PREFIX",
        ],
    )
    cli_image = env.get("WORDPRESS_CLI_IMAGE", "wordpress:cli-php8.3")
    wordpress_container_name = wordpress_container(env)
    title = env.get("WORDPRESS_MULTISITE_TITLE", "OpenDock WordPress Network")

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "shared-net",
        "--volumes-from",
        wordpress_container_name,
        "-e",
        f"WORDPRESS_DB_HOST={env['WORDPRESS_DB_HOST']}",
        "-e",
        f"WORDPRESS_DB_NAME={env['WORDPRESS_DB_NAME']}",
        "-e",
        f"WORDPRESS_DB_USER={env['WORDPRESS_DB_USER']}",
        "-e",
        f"WORDPRESS_DB_PASSWORD={env['WORDPRESS_DB_PASSWORD']}",
        "-e",
        f"WORDPRESS_TABLE_PREFIX={env['WORDPRESS_TABLE_PREFIX']}",
        cli_image,
        f"--url=https://{hostname}",
        "core",
        "multisite-convert",
        "--path=/var/www/html",
        "--base=/",
        f"--title={title}",
    ]

    print("==> wordpress: convert database to multisite")
    try:
        result = capture(command)
    except subprocess.CalledProcessError as error:
        print_command_output(error)
        raise SystemExit(
            "\nWP-CLI could not convert the WordPress database.\n"
            "Backups were created before this step. Review the error above before retrying."
        ) from error

    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    for line in output.splitlines():
        if "Multisite constants could not be written" in line:
            print(
                "  WP-CLI could not write multisite constants; "
                "OpenDock will patch wp-config.php next."
            )
        elif line.startswith("define(") or line.startswith("$base ="):
            continue
        else:
            print(f"  {line}")
    print(f"  Network host: {hostname}")


def restart_wordpress(env):
    container = wordpress_container(env)
    print("==> wordpress: restart")
    run(["docker", "restart", container])


def main():
    parser = argparse.ArgumentParser(
        description="Enable WordPress subdirectory multisite for OpenDock."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    args = parser.parse_args()

    env = load_env()
    hostname = wordpress_hostname(env)
    ensure_runtime(env)
    container = wordpress_container(env)
    ensure_files(env)
    confirm(args, hostname)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ensure_htaccess(container)
    temp_dir = Path(tempfile.mkdtemp(prefix="opendock-wp-multisite-"))
    config = temp_dir / "wp-config.php"
    htaccess = temp_dir / ".htaccess"
    copy_from_container(container, "wp-config.php", config)
    copy_from_container(container, ".htaccess", htaccess)
    already_multisite = has_multisite_config(config)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print("==> wordpress: backup files")
    backup_file(container, "wp-config.php", timestamp)
    backup_file(container, ".htaccess", timestamp)

    print("==> wordpress: backup database")
    backup_database(env, timestamp)

    if already_multisite:
        print("==> wordpress: convert database to multisite")
        print("  Already enabled in wp-config.php; skipping WP-CLI conversion.")
    else:
        wp_cli_convert(env, hostname)

    print("==> wordpress: update multisite files")
    https_status = patch_https_config(config)
    config_status = patch_wp_config(config, hostname)
    htaccess_status = patch_htaccess(htaccess)
    copy_to_container(container, config, "wp-config.php")
    copy_to_container(container, htaccess, ".htaccess")
    print(f"  HTTPS proxy config: {https_status}")
    print(f"  wp-config.php: {config_status}")
    print(f"  .htaccess: {htaccess_status}")

    restart_wordpress(env)

    print()
    print("WordPress subdirectory multisite is enabled.")
    print()
    print("Open:")
    print(f"  https://{hostname}/wp-admin/network/")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        raise SystemExit("Canceled.")
