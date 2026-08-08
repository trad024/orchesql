"""
Shared state contract for the orchesql orchestrator graph.

Every agent node reads from and writes to this single object. LangGraph
passes it between nodes, and the FastAPI layer serializes it directly at
the API boundary (since it's already a Pydantic model, no separate DTOs
needed). Getting this shape right now matters more than any other file
in the project -- every agent written after this depends on these
fields existing and meaning what they say they mean.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Status(str, Enum):
    """Drives orchestrator routing. The orchestrator's only job is to
    read this field and decide which node runs next. Nothing else
    should encode routing logic."""

    NEW = "new"
    NEEDS_SCHEMA = "needs_schema"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_GENERATION = "needs_generation"
    NEEDS_VALIDATION = "needs_validation"
    NEEDS_EXECUTION = "needs_execution"
    DONE = "done"
    FAILED = "failed"


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class SchemaColumn(BaseModel):
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False


class SchemaTable(BaseModel):
    name: str
    columns: list[SchemaColumn] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)


class SchemaContext(BaseModel):
    """The pruned schema subset discovery selected for this question --
    NOT the full database. This is the only view of the database the
    LLM ever receives. It never contains rows."""

    tables: list[SchemaTable] = Field(default_factory=list)
    confidence: float = 0.0
    candidate_ambiguities: list[str] = Field(default_factory=list)


class ClarificationRequest(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list)


class SQLAttempt(BaseModel):
    sql: str
    validation_errors: list[str] = Field(default_factory=list)
    execution_error: Optional[str] = None


class ExecutionResult(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False


class GraphState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    status: Status = Status.NEW
    retry_count: int = 0
    max_retries: int = 3

    schema_context: Optional[SchemaContext] = None

    clarification_request: Optional[ClarificationRequest] = None
    clarification_response: Optional[str] = None

    attempts: list[SQLAttempt] = Field(default_factory=list)
    generated_sql: Optional[str] = None
    results: Optional[ExecutionResult] = None

    error: Optional[str] = None

    model_config = {"extra": "forbid"}
