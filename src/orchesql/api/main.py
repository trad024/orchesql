"""FastAPI app for orchesql."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel

from orchesql.adapters.postgres import introspect_schema
from orchesql.orchestrator.graph import build_graph
from orchesql.orchestrator.state import GraphState, Status
from orchesql.orchestrator.tracing import get_tracer

load_dotenv()

_graph = None


def _get_llm_call():
    """Return an LLM callable backed by Groq's OpenAI-compatible API."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )
    model = os.getenv("ORCHESQL_MODEL", "llama-3.3-70b-versatile")

    def call(messages: list[dict]) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2048,
        )
        return resp.choices[0].message.content

    return call


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    conn_str = os.getenv("DATABASE_URL")
    if conn_str:
        schema = introspect_schema(conn_str)
        _graph = build_graph(schema, conn_str, _get_llm_call())
    yield


app = FastAPI(title="orchesql", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ORCHESQL_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


class ClarifyRequest(BaseModel):
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


def _thread_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _to_response(session_id: str, result: dict) -> dict:
    """Turn a raw graph.invoke() result into an API response, handling
    the interrupt (clarification-needed) case."""
    interrupts = result.pop("__interrupt__", None)
    if interrupts:
        return {
            "session_id": session_id,
            "status": Status.NEEDS_CLARIFICATION.value,
            "clarification": interrupts[0].value,
        }

    state = GraphState(**result)
    return {
        "session_id": session_id,
        "status": state.status.value,
        "sql": state.generated_sql,
        "explanation": state.explanation,
        "results": state.results.model_dump() if state.results else None,
        "error": state.error,
    }


@app.post("/query")
async def query(req: QueryRequest):
    if not _graph:
        raise HTTPException(503, "No database configured (set DATABASE_URL)")

    session_id = str(uuid4())
    state = GraphState(session_id=session_id, question=req.question)
    with get_tracer().start_as_current_span("query") as span:
        span.set_attribute("orchesql.session_id", session_id)
        result = _graph.invoke(state, config=_thread_config(session_id))
    return _to_response(session_id, result)


@app.post("/query/{session_id}/clarify")
async def clarify(session_id: str, req: ClarifyRequest):
    if not _graph:
        raise HTTPException(503, "No database configured")

    config = _thread_config(session_id)
    if not _graph.get_state(config).values:
        raise HTTPException(404, "Session not found")

    with get_tracer().start_as_current_span("clarify") as span:
        span.set_attribute("orchesql.session_id", session_id)
        result = _graph.invoke(Command(resume=req.answer), config=config)
    return _to_response(session_id, result)
