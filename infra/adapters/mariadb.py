"""Removal adapter for service-owned objects in the shared MariaDB server."""


def removal_request(container: str, database: str, role: str) -> tuple[list[str], str]:
    sql = (
        f"DROP DATABASE IF EXISTS `{database}`;\n"
        f"DROP USER IF EXISTS '{role}'@'%';\n"
        "FLUSH PRIVILEGES;\n"
    )
    command = [
        "docker", "exec", "-i", container, "sh", "-c",
        'exec mariadb --user=root --password="$MYSQL_ROOT_PASSWORD" --batch',
    ]
    return command, sql
