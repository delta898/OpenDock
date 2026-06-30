#!/usr/bin/env python3
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
COMMON_ENV = ROOT_DIR / "common.env"
SERVICE_DIR = ROOT_DIR / "services" / "mastodon"
SERVICE_ENV = SERVICE_DIR / ".env"
COMPOSE_FILE = SERVICE_DIR / "compose.yml"
RESERVED_USERNAMES = {"admin"}


def parse_env(path):
    values = {}
    if not path.exists():
        return values

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")

    return values


def load_env():
    env = {}
    env.update(parse_env(COMMON_ENV))
    env.update(parse_env(SERVICE_ENV))
    return env


def require_env(env, names):
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise SystemExit(
            "Mastodon owner account is not configured.\n\n"
            f"Missing values: {' '.join(missing)}\n\n"
            "Run:\n"
            "  make setup mastodon"
        )


def validate_username(env):
    username = env["MASTODON_ADMIN_USERNAME"]
    if username.lower() in RESERVED_USERNAMES:
        raise SystemExit(
            "Mastodon owner username is reserved by Mastodon.\n\n"
            f"Current value: MASTODON_ADMIN_USERNAME={username}\n\n"
            "Set a different username, for example:\n"
            "  MASTODON_ADMIN_USERNAME=opendock\n\n"
            "Then run:\n"
            "  make launch mastodon"
        )


def compose_run(env, *command, capture_output=False):
    compose = [
        "docker",
        "compose",
        "--project-directory",
        str(SERVICE_DIR),
        "--env-file",
        str(COMMON_ENV),
        "--env-file",
        str(SERVICE_ENV),
        "-f",
        str(COMPOSE_FILE),
        "run",
        "--rm",
        "--no-deps",
        "-e",
        f"MASTODON_ADMIN_USERNAME={env['MASTODON_ADMIN_USERNAME']}",
        "-e",
        f"MASTODON_ADMIN_EMAIL={env['MASTODON_ADMIN_EMAIL']}",
        "-e",
        f"MASTODON_ADMIN_PASSWORD={env['MASTODON_ADMIN_PASSWORD']}",
        "mastodon-web",
        *command,
    ]
    try:
        return subprocess.run(
            compose,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
        )
    except FileNotFoundError as error:
        raise SystemExit("Docker is required to bootstrap Mastodon.") from error


def rails_eval(env, code):
    try:
        result = compose_run(env, "bin/rails", "runner", code, capture_output=True)
    except subprocess.CalledProcessError as error:
        output = command_output(error)
        raise SystemExit(f"Could not query Mastodon with Rails runner.\n{output}") from error

    return result.stdout.strip()


def command_output(error):
    return "\n".join(
        part.strip() for part in (error.stdout, error.stderr) if part.strip()
    )


def last_answer(output):
    lines = output.splitlines()
    if not lines:
        raise SystemExit("Mastodon command returned no output.")
    return lines[-1]


def owner_exists(env):
    code = """
owner_role = UserRole.where('lower(name) = ?', 'owner').first
exists = owner_role && User.where(role_id: owner_role.id).exists?
puts(exists ? 'yes' : 'no')
"""
    return last_answer(rails_eval(env, code)) == "yes"


def admin_account_exists(env):
    code = """
username = ENV.fetch('MASTODON_ADMIN_USERNAME')
account = if Account.respond_to?(:find_local)
  Account.find_local(username)
else
  Account.find_by(username: username, domain: nil)
end
puts(account && account.user ? 'yes' : 'no')
"""
    return last_answer(rails_eval(env, code)) == "yes"


def create_owner(env):
    command = [
        "bin/tootctl",
        "accounts",
        "create",
        env["MASTODON_ADMIN_USERNAME"],
        "--email",
        env["MASTODON_ADMIN_EMAIL"],
        "--confirmed",
        "--role",
        "Owner",
    ]

    try:
        compose_run(env, *command, capture_output=True)
    except subprocess.CalledProcessError as error:
        output = command_output(error)
        raise SystemExit(f"Could not create Mastodon owner account.\n{output}") from error


def set_created_owner_password(env):
    code = r"""
username = ENV.fetch('MASTODON_ADMIN_USERNAME')
email = ENV.fetch('MASTODON_ADMIN_EMAIL').downcase
password = ENV.fetch('MASTODON_ADMIN_PASSWORD')
account = if Account.respond_to?(:find_local)
  Account.find_local(username)
else
  Account.find_by(username: username, domain: nil)
end
raise "Mastodon account not found: #{username}" unless account && account.user

user = account.user
owner_role = UserRole.where('lower(name) = ?', 'owner').first
user.role = owner_role if owner_role
user.email = email
user.confirmed_at ||= Time.now.utc
user.approved = true if user.respond_to?(:approved=)
user.password = password
user.password_confirmation = password
user.save!
puts 'password-set'
"""
    output = rails_eval(env, code)
    if "password-set" not in output:
        raise SystemExit("Could not set Mastodon owner password.")


def print_ready(env):
    print("Mastodon owner account is ready.")
    print(f"Login email: {env['MASTODON_ADMIN_EMAIL']}")
    print(f"Login username: {env['MASTODON_ADMIN_USERNAME']}")
    print("Login password: MASTODON_ADMIN_PASSWORD in common.env")


def print_existing_account(env):
    print("Mastodon owner account already exists. No password was changed.")
    print()
    print("OpenDock only applies MASTODON_ADMIN_PASSWORD when it creates the owner account.")
    print("Use the Mastodon web UI to manage the existing account password.")
    print(f"Configured owner username: {env['MASTODON_ADMIN_USERNAME']}")


def main():
    env = load_env()
    require_env(
        env,
        [
            "MASTODON_ADMIN_USERNAME",
            "MASTODON_ADMIN_EMAIL",
            "MASTODON_ADMIN_PASSWORD",
        ],
    )
    validate_username(env)

    admin_exists = admin_account_exists(env)
    has_owner = owner_exists(env)

    if admin_exists:
        print_existing_account(env)
        return 0

    if has_owner:
        raise SystemExit(
            "A Mastodon owner account already exists, but it does not match "
            "MASTODON_ADMIN_USERNAME.\n\n"
            "OpenDock will not create or change another owner automatically."
        )

    create_owner(env)
    set_created_owner_password(env)
    print_ready(env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
