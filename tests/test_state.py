import pytest
from pydantic import ValidationError

from orchesql.orchestrator.state import GraphState, Status, SchemaContext, SchemaTable


def test_minimal_construction_sets_sane_defaults():
    state = GraphState(question="How many orders were placed last month?")
    assert state.status == Status.NEW
    assert state.session_id
    assert state.retry_count == 0


def test_unknown_fields_are_rejected_not_silently_dropped():
    with pytest.raises(ValidationError):
        GraphState(question="test", totally_made_up_field="oops")


def test_schema_context_round_trips_through_the_state():
    ctx = SchemaContext(
        tables=[SchemaTable(name="orders"), SchemaTable(name="customers")],
        confidence=0.92,
    )
    state = GraphState(question="test", schema_context=ctx, status=Status.NEEDS_GENERATION)
    assert state.schema_context.confidence == 0.92


def test_state_is_json_serializable_for_the_api_boundary():
    state = GraphState(question="test")
    restored = GraphState.model_validate_json(state.model_dump_json())
    assert restored.session_id == state.session_id
