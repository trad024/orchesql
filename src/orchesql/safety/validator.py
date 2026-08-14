"""SQL safety validation — sqlglot AST-based checks.

Rules enforced:
1. SELECT only (no DML/DDL)
2. No recursive CTEs
3. Every referenced table/column must exist in the provided schema context
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from orchesql.orchestrator.state import SchemaContext

_FORBIDDEN_KINDS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Grant, exp.Command,
)


def validate(sql: str, schema_context: SchemaContext | None = None) -> list[str]:
    """Parse SQL into AST and return a list of error strings. Empty list = safe."""
    errors: list[str] = []

    try:
        parsed = sqlglot.parse(sql)
    except sqlglot.errors.ParseError as e:
        return [f"Parse error: {e}"]

    if not parsed:
        return ["Empty SQL"]

    for statement in parsed:
        if statement is None:
            errors.append("Unparseable statement")
            continue

        if isinstance(statement, _FORBIDDEN_KINDS):
            errors.append(
                f"Forbidden statement type: {type(statement).__name__}"
            )
            continue

        if not isinstance(statement, exp.Select):
            errors.append(
                f"Only SELECT is allowed, got: {type(statement).__name__}"
            )
            continue

        for cte in statement.find_all(exp.CTE):
            props = cte.args.get("properties")
            if props:
                for prop in props.expressions if hasattr(props, "expressions") else []:
                    if isinstance(prop, exp.Property) and "RECURSIVE" in str(prop).upper():
                        errors.append("Recursive CTEs are not allowed")

        for node in statement.walk():
            if isinstance(node, exp.With) and node.args.get("recursive"):
                errors.append("Recursive CTEs are not allowed")
                break

    if schema_context and not errors:
        errors.extend(_check_references(parsed, schema_context))

    return errors


def _check_references(
    parsed: list[exp.Expression | None],
    schema_context: SchemaContext,
) -> list[str]:
    errors: list[str] = []
    known_tables = {t.name.lower() for t in schema_context.tables}
    known_columns: dict[str, set[str]] = {
        t.name.lower(): {c.name.lower() for c in t.columns}
        for t in schema_context.tables
    }
    all_columns = set()
    for cols in known_columns.values():
        all_columns |= cols

    for statement in parsed:
        if statement is None:
            continue
        for table in statement.find_all(exp.Table):
            tname = table.name.lower()
            if tname and tname not in known_tables:
                errors.append(f"Unknown table: {table.name}")

        for column in statement.find_all(exp.Column):
            cname = column.name.lower()
            table_ref = column.table
            if table_ref:
                tname = table_ref.lower()
                if tname in known_columns and cname not in known_columns[tname]:
                    errors.append(
                        f"Unknown column: {column.table}.{column.name}"
                    )
            else:
                if known_tables and cname not in all_columns:
                    errors.append(f"Unknown column: {column.name}")

    return errors
