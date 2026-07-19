"""
db.py
Handles all direct interaction with the SQLite database:
- producing a text description of the schema (for prompt grounding)
- executing SQL safely (read-only enforcement lives here as a second line
  of defense, in addition to the validator)
"""

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "ecommerce.db"


def get_connection() -> sqlite3.Connection:
    """Opens a read-only connection to the SQLite file.

    Using SQLite's URI mode with mode=ro means even if every other
    guardrail fails, the OS-level connection itself cannot perform writes.
    """
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_description() -> str:
    """Returns a human/LLM-readable description of the schema, built
    directly from SQLite's own metadata rather than hardcoded text --
    so it can never drift out of sync with the real database.
    """
    conn = get_connection()
    cur = conn.cursor()

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    lines = []
    for (table_name,) in tables:
        lines.append(f"Table: {table_name}")
        columns = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        for col in columns:
            # col: (cid, name, type, notnull, dflt_value, pk)
            col_desc = f"  - {col['name']} ({col['type']})"
            if col["pk"]:
                col_desc += " [PRIMARY KEY]"
            lines.append(col_desc)

        fks = cur.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        for fk in fks:
            lines.append(f"  - FOREIGN KEY: {fk['from']} -> {fk['table']}({fk['to']})")

        lines.append("")  # blank line between tables

    conn.close()
    return "\n".join(lines)


def get_schema_metadata() -> dict[str, list[str]]:
    """Returns {table_name: [column_names]} -- used by the validator to
    check whether the LLM's SQL references real tables/columns.
    """
    conn = get_connection()
    cur = conn.cursor()

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    metadata = {}
    for (table_name,) in tables:
        columns = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        metadata[table_name] = [col["name"] for col in columns]

    conn.close()
    return metadata


def execute_query(sql: str, limit: int = 100) -> list[dict[str, Any]]:
    """Executes a validated SELECT query and returns rows as a list of dicts.

    NOTE: this function assumes the SQL has already passed validation
    (validator.py). It does not re-check statement type -- that check
    belongs in one place (the validator) to avoid duplicated, drifting logic.
    A row cap is still applied here as a safety net against runaway result sets.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchmany(limit)
        return [dict(row) for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    # Quick manual check when running `python app/db.py` directly
    print("=== Schema description ===")
    print(get_schema_description())

    print("=== Schema metadata (for validator) ===")
    print(get_schema_metadata())

    print("=== Sample query ===")
    print(execute_query("SELECT full_name, country FROM customers LIMIT 3"))
