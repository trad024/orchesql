"""Postgres adapter — schema introspection and read-only query execution."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from orchesql.orchestrator.state import ForeignKey, SchemaColumn, SchemaTable


_COLUMNS_QUERY = """
SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.is_nullable,
    COALESCE(tc.constraint_type = 'PRIMARY KEY', false) AS is_primary_key
FROM information_schema.columns c
LEFT JOIN information_schema.key_column_usage kcu
    ON  c.table_schema = kcu.table_schema
    AND c.table_name   = kcu.table_name
    AND c.column_name  = kcu.column_name
LEFT JOIN information_schema.table_constraints tc
    ON  kcu.constraint_schema = tc.constraint_schema
    AND kcu.constraint_name   = tc.constraint_name
    AND tc.constraint_type    = 'PRIMARY KEY'
WHERE c.table_schema = 'public'
ORDER BY c.table_name, c.ordinal_position
"""

_FK_QUERY = """
SELECT
    kcu.table_name,
    kcu.column_name,
    ccu.table_name  AS references_table,
    ccu.column_name AS references_column
FROM information_schema.referential_constraints rc
JOIN information_schema.key_column_usage kcu
    ON  rc.constraint_schema = kcu.constraint_schema
    AND rc.constraint_name   = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON  rc.unique_constraint_schema = ccu.constraint_schema
    AND rc.unique_constraint_name   = ccu.constraint_name
WHERE kcu.table_schema = 'public'
ORDER BY kcu.table_name, kcu.column_name
"""

_MAX_ROWS = 500
_QUERY_TIMEOUT_S = 30


def introspect_schema(connection_string: str) -> list[SchemaTable]:
    """Return every public table with columns and foreign keys."""
    with psycopg.connect(connection_string, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(_COLUMNS_QUERY)
            col_rows = cur.fetchall()
            cur.execute(_FK_QUERY)
            fk_rows = cur.fetchall()

    tables: dict[str, SchemaTable] = {}
    for r in col_rows:
        tname = r["table_name"]
        if tname not in tables:
            tables[tname] = SchemaTable(name=tname)
        tables[tname].columns.append(
            SchemaColumn(
                name=r["column_name"],
                data_type=r["data_type"],
                is_nullable=r["is_nullable"] == "YES",
                is_primary_key=r["is_primary_key"],
            )
        )

    for r in fk_rows:
        tname = r["table_name"]
        if tname in tables:
            tables[tname].foreign_keys.append(
                ForeignKey(
                    column=r["column_name"],
                    references_table=r["references_table"],
                    references_column=r["references_column"],
                )
            )

    return list(tables.values())


def execute_query(
    connection_string: str,
    sql: str,
    *,
    max_rows: int = _MAX_ROWS,
    timeout_s: int = _QUERY_TIMEOUT_S,
) -> dict:
    """Execute a validated, read-only query. Returns {columns, rows, row_count, truncated}."""
    with psycopg.connect(
        connection_string,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn:
        conn.execute(f"SET statement_timeout = '{timeout_s}s'")
        with conn.cursor() as cur:
            cur.execute(sql)
            desc = cur.description
            columns = [d.name for d in desc] if desc else []
            rows = cur.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            if truncated:
                rows = rows[:max_rows]
            return {
                "columns": columns,
                "rows": [list(r.values()) for r in rows],
                "row_count": len(rows),
                "truncated": truncated,
            }
