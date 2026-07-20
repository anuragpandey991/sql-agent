import sqlglot
from sqlglot import exp

BLOCKED_STATEMENT_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
)


def validate_sql(
    sql: str,
    schema_metadata: dict[str, list[str]],
) -> list[str]:
    errors: list[str] = []
    sql = sql.strip()

    if not sql:
        return ["Empty SQL string."]

    if sql.startswith("```"):
        sql = sql.strip("`")
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()

    try:
        parsed = sqlglot.parse_one(
            sql,
            read="sqlite",
        )
    except Exception as e:
        return [f"SQL syntax error: {e}"]

    if isinstance(parsed, BLOCKED_STATEMENT_TYPES):
        errors.append(
            f"Blocked statement type '{type(parsed).__name__}'. "
            "Only SELECT queries are permitted."
        )
        return errors

    if not isinstance(parsed, exp.Select):
        errors.append(
            f"Only SELECT statements are permitted; got '{type(parsed).__name__}'."
        )
        return errors

    remainder = sql.split(";", 1)

    if len(remainder) > 1 and remainder[1].strip():
        errors.append(
            "Multiple SQL statements detected; only a single SELECT is permitted."
        )
        return errors

    known_tables = {
        t.lower() for t in schema_metadata.keys()
    }

    referenced_tables = {
        t.name.lower()
        for t in parsed.find_all(exp.Table)
    }

    unknown_tables = (
        referenced_tables - known_tables
    )

    if unknown_tables:
        errors.append(
            f"Unknown table(s) referenced: {', '.join(sorted(unknown_tables))}. "
            f"Known tables: {', '.join(sorted(known_tables))}."
        )
        return errors

    all_known_columns = set()

    for table in referenced_tables:
        all_known_columns.update(
            c.lower()
            for c in schema_metadata.get(table, [])
        )

    referenced_columns = {
        c.name.lower()
        for c in parsed.find_all(exp.Column)
        if c.name != "*"
    }

    defined_aliases = {
        a.alias.lower()
        for a in parsed.find_all(exp.Alias)
        if a.alias
    }

    unknown_columns = (
        referenced_columns
        - all_known_columns
        - defined_aliases
    )

    if unknown_columns:
        errors.append(
            f"Unknown column(s) referenced: {', '.join(sorted(unknown_columns))}. "
            f"Available columns in referenced tables: {', '.join(sorted(all_known_columns))}."
        )

    return errors


if __name__ == "__main__":
    from db import get_schema_metadata

    metadata = get_schema_metadata()

    test_cases = [
        (
            "valid select",
            "SELECT full_name, country FROM customers WHERE country = 'India'",
        ),
        (
            "valid join+agg",
            """
            SELECT c.full_name, SUM(oi.quantity * oi.price_at_purchase) AS total_spend
            FROM customers c
            JOIN orders o ON o.customer_id = c.customer_id
            JOIN order_items oi ON oi.order_id = o.order_id
            GROUP BY c.customer_id
            ORDER BY total_spend DESC
            LIMIT 5
            """,
        ),
        (
            "blocked delete",
            "DELETE FROM customers WHERE customer_id = 1",
        ),
        (
            "blocked drop",
            "DROP TABLE orders",
        ),
        (
            "sql injection attempt",
            "SELECT * FROM customers; DROP TABLE orders;",
        ),
        (
            "hallucinated column",
            "SELECT discount FROM customers",
        ),
        (
            "hallucinated table",
            "SELECT * FROM discounts",
        ),
        (
            "broken syntax",
            "SELEC * FROM customers",
        ),
    ]

    for label, sql in test_cases:
        errs = validate_sql(sql, metadata)
        status = (
            "PASS (valid)"
            if not errs
            else f"REJECTED: {errs}"
        )
        print(f"[{label}] -> {status}")
