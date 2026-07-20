import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "ecommerce.db"


def get_connection() -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_description() -> str:
    conn = get_connection()
    cur = conn.cursor()

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    lines = []

    for (table_name,) in tables:
        lines.append(f"Table: {table_name}")

        columns = cur.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()

        for col in columns:
            col_desc = f"  - {col['name']} ({col['type']})"

            if col["pk"]:
                col_desc += " [PRIMARY KEY]"

            lines.append(col_desc)

        fks = cur.execute(
            f"PRAGMA foreign_key_list({table_name})"
        ).fetchall()

        for fk in fks:
            lines.append(
                f"  - FOREIGN KEY: {fk['from']} -> {fk['table']}({fk['to']})"
            )

        lines.append("")

    conn.close()
    return "\n".join(lines)


def get_schema_metadata() -> dict[str, list[str]]:
    conn = get_connection()
    cur = conn.cursor()

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    metadata = {}

    for (table_name,) in tables:
        columns = cur.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()

        metadata[table_name] = [col["name"] for col in columns]

    conn.close()
    return metadata


def execute_query(
    sql: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(sql)
        rows = cur.fetchmany(limit)
        return [dict(row) for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    print("=== Schema description ===")
    print(get_schema_description())

    print("=== Schema metadata (for validator) ===")
    print(get_schema_metadata())

    print("=== Sample query ===")
    print(
        execute_query(
            "SELECT full_name, country FROM customers LIMIT 3"
        )
    )
