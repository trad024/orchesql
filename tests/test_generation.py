from orchesql.agents.generation import run, build_prompt
from orchesql.orchestrator.state import (
    GraphState, SchemaContext, SchemaTable, SchemaColumn, Status,
)


def _state_with_schema():
    ctx = SchemaContext(
        tables=[
            SchemaTable(
                name="orders",
                columns=[
                    SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                    SchemaColumn(name="total", data_type="numeric"),
                ],
            )
        ],
        confidence=0.95,
    )
    return GraphState(
        question="How many orders?",
        schema_context=ctx,
        status=Status.NEEDS_GENERATION,
    )


def test_valid_sql_moves_to_execution():
    state = _state_with_schema()
    result = run(state, llm_call=lambda _: "SELECT count(*) FROM orders")
    assert result.status == Status.NEEDS_EXECUTION
    assert result.generated_sql == "SELECT count(*) FROM orders"


def test_invalid_sql_retries():
    state = _state_with_schema()
    result = run(state, llm_call=lambda _: "DELETE FROM orders")
    assert result.status == Status.NEEDS_GENERATION
    assert result.retry_count == 1
    assert len(result.attempts) == 1


def test_max_retries_fails():
    state = _state_with_schema()
    state.retry_count = 2
    state.max_retries = 3
    result = run(state, llm_call=lambda _: "DROP TABLE orders")
    assert result.status == Status.FAILED


def test_strips_markdown_fences():
    state = _state_with_schema()
    result = run(state, llm_call=lambda _: "```sql\nSELECT count(*) FROM orders\n```")
    assert result.status == Status.NEEDS_EXECUTION


def test_structured_response_parses_sql_and_explanation():
    state = _state_with_schema()
    reply = "SQL: SELECT count(*) FROM orders\nEXPLANATION: Counts all orders."
    result = run(state, llm_call=lambda _: reply)
    assert result.status == Status.NEEDS_EXECUTION
    assert result.generated_sql == "SELECT count(*) FROM orders"
    assert result.explanation == "Counts all orders."


def test_build_prompt_includes_schema():
    state = _state_with_schema()
    msgs = build_prompt(state)
    assert any("orders" in m["content"] for m in msgs)
