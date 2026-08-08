"""Postgres adapter -- future step."""


def introspect_schema(connection_string: str):
    """Will introspect a Postgres database's tables, columns, and
    foreign keys."""
    raise NotImplementedError


def execute_query(connection_string: str, sql: str):
    """Will execute a validated, read-only query against Postgres."""
    raise NotImplementedError
