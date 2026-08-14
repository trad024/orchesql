from langgraph.types import Command

from orchesql.orchestrator.graph import build_graph
from orchesql.orchestrator.state import GraphState, SchemaColumn, SchemaTable


def _ambiguous_schema():
    # Two unrelated tables that both match the question's tokens equally,
    # so schema_discovery reports a tie and routes to disambiguation.
    return [
        SchemaTable(name="a", columns=[SchemaColumn(name="widget", data_type="text")]),
        SchemaTable(name="b", columns=[SchemaColumn(name="widget", data_type="text")]),
    ]


def _fake_execute_query(connection_string, sql, **kwargs):
    return {"columns": ["n"], "rows": [[1]], "row_count": 1, "truncated": False}


def test_interrupt_then_resume_reaches_execution(monkeypatch):
    monkeypatch.setattr(
        "orchesql.agents.execution.postgres.execute_query", _fake_execute_query
    )

    graph = build_graph(
        _ambiguous_schema(),
        connection_string="postgresql://fake",
        llm_call=lambda _: "SELECT widget FROM a",
    )

    config = {"configurable": {"thread_id": "test-thread"}}
    state = GraphState(session_id="test-thread", question="widget widget")

    result1 = graph.invoke(state, config=config)
    assert "__interrupt__" in result1
    interrupt_value = result1["__interrupt__"][0].value
    assert "options" in interrupt_value

    result2 = graph.invoke(Command(resume="a"), config=config)
    assert "__interrupt__" not in result2
    assert result2["status"] == "done"
    assert result2["generated_sql"] == "SELECT widget FROM a"
    assert result2["results"].row_count == 1
