#!/usr/bin/env python3
import json
import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT_DIR / "services" / "supabase"
COMMON_ENV = ROOT_DIR / "common.env"
SERVICE_ENV = SERVICE_DIR / ".env"


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
    values = {}
    values.update(parse_env(COMMON_ENV))
    values.update(parse_env(SERVICE_ENV))
    return values


def run(*command):
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
    except FileNotFoundError as error:
        raise SystemExit("Docker is required to verify Supabase.") from error
    except subprocess.CalledProcessError as error:
        details = "\n".join(
            output.strip() for output in (error.stdout, error.stderr) if output.strip()
        )
        raise SystemExit(f"Supabase smoke test command failed.\n{details}") from error


def check_containers(env):
    names = [
        env["SUPABASE_DB_CONTAINER_NAME"],
        env["SUPABASE_AUTH_CONTAINER_NAME"],
        env["SUPABASE_REST_CONTAINER_NAME"],
        "realtime-dev.supabase-realtime",
        env["SUPABASE_STORAGE_CONTAINER_NAME"],
        env["SUPABASE_IMGPROXY_CONTAINER_NAME"],
        env["SUPABASE_PG_META_CONTAINER_NAME"],
        env["SUPABASE_STUDIO_CONTAINER_NAME"],
        env["SUPABASE_KONG_CONTAINER_NAME"],
        env["SUPABASE_EDGE_RUNTIME_CONTAINER_NAME"],
        env["SUPABASE_INBUCKET_CONTAINER_NAME"],
    ]

    failures = []
    for _attempt in range(30):
        failures = []
        for name in names:
            raw_state = run("docker", "inspect", "--format", "{{json .State}}", name)
            state = json.loads(raw_state)
            health = state.get("Health", {}).get("Status")
            if not state.get("Running") or (health and health != "healthy"):
                failures.append(
                    f"{name}: status={state.get('Status')} health={health or 'n/a'}"
                )
        if not failures:
            break
        time.sleep(2)

    if failures:
        raise SystemExit("Supabase containers are not ready:\n  " + "\n  ".join(failures))

    print(f"  OK containers ({len(names)})")


def check_database(env):
    sql = """
SELECT json_build_object(
  'schemas', (
    SELECT count(*) FROM pg_namespace
    WHERE nspname IN ('auth', 'storage', '_realtime', 'graphql_public')
  ),
  'roles', (
    SELECT count(*) FROM pg_roles
    WHERE rolname IN (
      'authenticator', 'supabase_auth_admin', 'supabase_functions_admin',
      'supabase_storage_admin', 'service_role'
    )
  ),
  'auth_users', to_regclass('auth.users') IS NOT NULL
);
"""
    output = run(
        "docker",
        "exec",
        env["SUPABASE_DB_CONTAINER_NAME"],
        "psql",
        "--host=localhost",
        "--username=postgres",
        "--dbname=postgres",
        "--tuples-only",
        "--no-align",
        "--command",
        sql,
    )
    result = json.loads(output)
    if result != {"schemas": 4, "roles": 5, "auth_users": True}:
        raise SystemExit(f"Supabase database contract failed: {result}")
    print("  OK database schemas and roles")


def check_http(env):
    node_script = r"""
const anon = process.env.SUPABASE_ANON_KEY;
const base = process.env.SUPABASE_URL;
const authenticatedHeaders = {
  apikey: anon,
  Authorization: `Bearer ${anon}`,
};

async function main() {
const checks = [
  ['auth', `${base}/auth/v1/health`, { headers: authenticatedHeaders }],
  ['rest', `${base}/rest/v1/`, { headers: authenticatedHeaders }],
  ['graphql', `${base}/graphql/v1`, {
    method: 'POST',
    headers: { ...authenticatedHeaders, 'content-type': 'application/json' },
    body: JSON.stringify({ query: '{ __typename }' }),
  }],
  ['storage', `${base}/storage/v1/status`, { headers: authenticatedHeaders }],
  ['edge-function', `${base}/functions/v1/hello`, { headers: authenticatedHeaders }],
  ['realtime', 'http://realtime-dev.supabase-realtime:4000/api/tenants/realtime-dev/health', {
    headers: { Authorization: `Bearer ${anon}` },
  }],
  ['studio', 'http://localhost:3000/api/platform/profile', {}],
];

const results = [];
for (const [name, url, options] of checks) {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(10000),
  });
  const body = await response.text();
  if (!response.ok) {
    throw new Error(`${name}: HTTP ${response.status}: ${body.slice(0, 200)}`);
  }
  if (name === 'graphql') {
    const payload = JSON.parse(body);
    if (payload.errors || payload.data?.__typename !== 'Query') {
      throw new Error(`graphql: unexpected response: ${body.slice(0, 200)}`);
    }
  }
  if (name === 'edge-function') {
    const payload = JSON.parse(body);
    if (!payload.message) {
      throw new Error(`edge-function: unexpected response: ${body.slice(0, 200)}`);
    }
  }
  results.push({ name, status: response.status });
}
process.stdout.write(JSON.stringify(results));
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
"""

    output = run(
        "docker",
        "exec",
        env["SUPABASE_STUDIO_CONTAINER_NAME"],
        "node",
        "-e",
        node_script,
    )
    results = json.loads(output)
    for result in results:
        print(f"  OK {result['name']} (HTTP {result['status']})")


def main():
    env = load_env()
    required = [
        "SUPABASE_DB_CONTAINER_NAME",
        "SUPABASE_AUTH_CONTAINER_NAME",
        "SUPABASE_REST_CONTAINER_NAME",
        "SUPABASE_STORAGE_CONTAINER_NAME",
        "SUPABASE_IMGPROXY_CONTAINER_NAME",
        "SUPABASE_PG_META_CONTAINER_NAME",
        "SUPABASE_STUDIO_CONTAINER_NAME",
        "SUPABASE_KONG_CONTAINER_NAME",
        "SUPABASE_EDGE_RUNTIME_CONTAINER_NAME",
        "SUPABASE_INBUCKET_CONTAINER_NAME",
    ]
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise SystemExit("Missing Supabase smoke-test settings: " + " ".join(missing))

    print("Supabase smoke tests:")
    check_containers(env)
    check_database(env)
    check_http(env)
    print("Supabase is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
