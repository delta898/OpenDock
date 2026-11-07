"""Removal adapter for service-owned objects in the shared PostgreSQL server."""


def removal_request(container: str, database: str, role: str) -> tuple[list[str], str]:
    sql = f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);\nDROP ROLE IF EXISTS "{role}";\n'
    command = [
        "docker", "exec", "-i", container, "sh", "-c",
        'exec psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1',
    ]
    return command, sql
