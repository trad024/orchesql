"""Orchestrator graph — LangGraph StateGraph wiring all agents together.

Routing is purely deterministic: read state.status, go to the matching node.
No LLM call for routing.
"""

from __future__ import annotations

from typing import Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from langgraph.errors import GraphInterrupt

from orchesql.agents import disambiguation, execution, generation, schema_discovery
from orchesql.orchestrator.state import GraphState, SchemaTable, Status
from orchesql.orchestrator.tracing import get_tracer


def _traced(name: str, fn: Callable[[GraphState], GraphState]) -> Callable[[GraphState], GraphState]:
    def wrapper(state: GraphState) -> GraphState:
        tracer = get_tracer()
        # record_exception/set_status_on_exception off: a GraphInterrupt here
        # means "paused for human input", not a failure -- agents already
        # encode real failures via GraphState.status/error, captured below
        with tracer.start_as_current_span(
            name, record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_attribute("orchesql.session_id", state.session_id)
            span.set_attribute("orchesql.status_in", state.status.value)
            try:
                result = fn(state)
            except GraphInterrupt:
                span.set_attribute("orchesql.status_out", "interrupted")
                raise
            span.set_attribute("orchesql.status_out", result.status.value)
            return result

    return wrapper


def _router(state: GraphState) -> str:
    return {
        Status.NEW: "schema_discovery",
        Status.NEEDS_SCHEMA: "schema_discovery",
        Status.NEEDS_CLARIFICATION: "disambiguation",
        Status.NEEDS_GENERATION: "generation",
        Status.NEEDS_EXECUTION: "execution",
        Status.DONE: END,
        Status.FAILED: END,
    }.get(state.status, END)


def build_graph(
    full_schema: list[SchemaTable],
    connection_string: str,
    llm_call: Callable,
) -> StateGraph:
    """Assemble and compile the orchestrator graph.

    Args:
        full_schema: pre-loaded via introspect_schema()
        connection_string: for the execution agent
        llm_call: callable(messages) -> str, injected for testability
    """
    graph = StateGraph(GraphState)

    graph.add_node(
        "schema_discovery",
        _traced("schema_discovery", lambda s: schema_discovery.run(s, full_schema)),
    )
    graph.add_node("disambiguation", _traced("disambiguation", disambiguation.run))
    graph.add_node(
        "generation",
        _traced("generation", lambda s: generation.run(s, llm_call=llm_call)),
    )
    graph.add_node(
        "execution",
        _traced("execution", lambda s: execution.run(s, connection_string=connection_string)),
    )

    graph.set_conditional_entry_point(_router)
    for node in ["schema_discovery", "disambiguation", "generation", "execution"]:
        graph.add_conditional_edges(node, _router)

    # ponytail: in-memory checkpointer, swap for a persistent one (Postgres/Redis)
    # when the API needs to survive a restart mid-clarification
    return graph.compile(checkpointer=MemorySaver())
