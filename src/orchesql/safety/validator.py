"""SQL safety validation -- future step."""


def validate(sql: str, schema_context=None):
    """Will use sqlglot to enforce SELECT-only and catch hallucinated
    tables/columns."""
    raise NotImplementedError
