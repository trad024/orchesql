"""SQL generation agent — MAC-SQL-style decomposition.

Sends only schema metadata to the LLM, never row data. Breaks the question
into sub-steps with chain-of-thought before producing SQL.
"""

from __future__ import annotations

import re

from orchesql.orchestrator.state import GraphState, SQLAttempt, Status
from orchesql.safety import validator

_RESPONSE_RE = re.compile(
    r"SQL:\s*(?P<sql>.+?)\s*EXPLANATION:\s*(?P<explanation>.+)", re.DOTALL
)


def _schema_to_prompt(state: GraphState) -> str:
    """Format the pruned schema as a text block for the LLM prompt."""
    if not state.schema_context:
        return "No schema available."

    lines: list[str] = []
    for t in state.schema_context.tables:
        cols = ", ".join(
            f"{c.name} ({c.data_type}{'  PK' if c.is_primary_key else ''})"
            for c in t.columns
        )
        lines.append(f"  {t.name}: [{cols}]")

        for fk in t.foreign_keys:
            lines.append(
                f"    FK: {fk.column} -> {fk.references_table}.{fk.references_column}"
            )

    return "Tables:\n" + "\n".join(lines)


def build_prompt(state: GraphState) -> list[dict[str, str]]:
    """Build the chat messages for the LLM call. Exported so callers can
    inspect/test the prompt without making an actual LLM call."""
    schema_text = _schema_to_prompt(state)
    prior_attempts = ""
    if state.attempts:
        prior_attempts = "\n\nPrior failed attempts (learn from these):\n"
        for i, a in enumerate(state.attempts, 1):
            errs = "; ".join(a.validation_errors) or a.execution_error or "unknown"
            prior_attempts += f"  Attempt {i}: {a.sql}\n    Errors: {errs}\n"

    system = (
        "You are a SQL generation assistant. You ONLY see schema metadata — "
        "table names, column names, types, and foreign keys. You NEVER see "
        "actual row data.\n\n"
        "Given a natural language question and a database schema, produce a "
        "single SELECT query that answers the question.\n\n"
        "Think step-by-step:\n"
        "1. Identify which tables are needed\n"
        "2. Determine the join path via foreign keys\n"
        "3. Identify filters, aggregations, and ordering\n"
        "4. Write the final SQL\n\n"
        "Reply in exactly this format, no markdown fences:\n"
        "SQL: <the query on one line>\n"
        "EXPLANATION: <one sentence describing what the query does>"
    )

    user_msg = f"Schema:\n{schema_text}\n\nQuestion: {state.question}"
    if state.clarification_response:
        user_msg += (
            f"\n\nThe user was asked to disambiguate and confirmed this "
            f"question is specifically about the `{state.clarification_response}` "
            f"table. The schema above may include other tables reachable via "
            f"foreign key for joins, but prefer `{state.clarification_response}` "
            f"wherever the question is otherwise ambiguous (e.g. which table's "
            f"name/id/etc. column to use)."
        )
    if prior_attempts:
        user_msg += prior_attempts

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]


def _parse_response(raw: str) -> tuple[str, str | None]:
    """Split a 'SQL: ... EXPLANATION: ...' response. Falls back to treating
    the whole reply as SQL if the model didn't follow the format."""
    match = _RESPONSE_RE.search(raw)
    if not match:
        sql = raw.strip()
        if sql.startswith("```"):
            sql = sql.strip("`").removeprefix("sql").strip()
        return sql, None

    sql = match.group("sql").strip()
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    explanation = match.group("explanation").strip()
    return sql, explanation


def run(state: GraphState, *, llm_call) -> GraphState:
    """Orchestrator node: generate SQL + explanation via LLM, then validate.

    llm_call: a callable(messages: list[dict]) -> str that returns the raw
    reply. Injected so the agent is testable without a live LLM.
    """
    messages = build_prompt(state)
    raw_sql, explanation = _parse_response(llm_call(messages))

    errors = validator.validate(raw_sql, state.schema_context)

    if errors:
        state.attempts.append(SQLAttempt(sql=raw_sql, validation_errors=errors))
        state.retry_count += 1
        if state.retry_count >= state.max_retries:
            state.status = Status.FAILED
            state.error = f"Max retries exceeded. Last errors: {'; '.join(errors)}"
        else:
            state.status = Status.NEEDS_GENERATION
    else:
        state.generated_sql = raw_sql
        state.explanation = explanation
        state.status = Status.NEEDS_EXECUTION

    return state
