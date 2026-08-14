"""Disambiguation agent — pauses the graph to ask the user a structured
multiple-choice question when schema discovery confidence is low."""

from __future__ import annotations

from langgraph.types import interrupt

from orchesql.orchestrator.state import (
    ClarificationRequest,
    GraphState,
    Status,
)


def run(state: GraphState) -> GraphState:
    """If ambiguities exist, interrupt with a multiple-choice question.
    On resume, the orchestrator should have set clarification_response."""

    ambiguities = (
        state.schema_context.candidate_ambiguities
        if state.schema_context
        else []
    )

    if not ambiguities:
        state.status = Status.NEEDS_GENERATION
        return state

    question = (
        f"The question could relate to several tables: "
        f"{', '.join(ambiguities)}. Which one did you mean?"
    )
    state.clarification_request = ClarificationRequest(
        question=question,
        options=ambiguities,
    )
    state.status = Status.NEEDS_CLARIFICATION

    answer = interrupt(state.clarification_request.model_dump())

    state.clarification_response = answer
    state.clarification_request = None
    state.status = Status.NEEDS_SCHEMA
    return state
