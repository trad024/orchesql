"""Execution agent — runs validated SQL via the adapter layer."""

from __future__ import annotations

from orchesql.adapters import postgres
from orchesql.orchestrator.state import (
    ExecutionResult,
    GraphState,
    SQLAttempt,
    Status,
)


def run(state: GraphState, *, connection_string: str) -> GraphState:
    """Execute state.generated_sql against the database. On failure,
    record the error and route back to generation for retry."""

    if not state.generated_sql:
        state.status = Status.FAILED
        state.error = "No SQL to execute"
        return state

    try:
        result = postgres.execute_query(connection_string, state.generated_sql)
        state.results = ExecutionResult(**result)
        state.status = Status.DONE
    except Exception as exc:
        state.attempts.append(
            SQLAttempt(sql=state.generated_sql, execution_error=str(exc))
        )
        state.generated_sql = None
        state.retry_count += 1
        if state.retry_count >= state.max_retries:
            state.status = Status.FAILED
            state.error = f"Max retries exceeded. Last error: {exc}"
        else:
            state.status = Status.NEEDS_GENERATION

    return state
