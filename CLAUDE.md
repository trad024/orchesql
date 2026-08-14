# OrcheSQL

Multi-agent orchestration system that converts natural language questions
into SQL against large, real production databases (200+ tables), without
ever routing raw row data through the LLM.

## Core architectural principle (non-negotiable)

The LLM only ever sees schema metadata — table names, column names, types,
foreign-key relationships. It never sees row data. Raw data stays inside
the client's environment at all times. Every design decision downstream of
this file should respect that boundary. If a change would let a row of
real data reach an LLM call, don't make it — flag it instead.

## Architecture: an orchestrator loop, not a pipeline

A central orchestrator (LangGraph `StateGraph`) reads a shared `GraphState`
object and routes to one of four agents based on its `status` field:

1. **schema_discovery** — deterministic, no LLM call. Resolves seed tables
   from the question, expands via BFS through a pre-built foreign-key
   graph. Returns a pruned schema subset + a confidence score.
2. **disambiguation** — triggers when confidence is low or multiple tables
   match equally. Uses LangGraph's `interrupt()`/resume to pause the graph,
   surface a structured (multiple-choice, not open-text) clarifying
   question, and resume from that exact point once answered.
3. **generation** — MAC-SQL-style decomposition: breaks the question into
   sub-steps with chain-of-thought before producing SQL. Uses only the
   pruned schema from step 1, never the full schema.
4. **execution** — runs only already-validated SQL, inside a sandboxed,
   read-only, timeout-bound worker.

Between generation and execution: every query is parsed with `sqlglot`
into an AST before being treated as executable — SELECT-only, no
recursive CTEs, no DML/DDL, every referenced table/column cross-checked
against the schema store to catch hallucinated names. This gate must exist
before execution is wired up, not after — a comparable open-source project
(MAC-SQL) shipped without it and had a documented DoS vulnerability via
resource-exhausting queries.

A bounded retry/refiner loop connects execution failures back to
generation. Each failed attempt (and why it failed) is kept in
`GraphState.attempts` so retries have real context, not blind resubmission.

The orchestrator's routing logic should stay deterministic and
inspectable — reserve LLM calls for agents that need reasoning
(disambiguation phrasing, generation), not for the routing decision
itself.

## Tech stack

- Python 3.11+, LangGraph, Pydantic (`GraphState` is the single contract
  every node reads/writes — see `src/orchesql/orchestrator/state.py`)
- sqlglot for AST-based SQL parsing/validation
- FastAPI (async) for the API layer
- First target engine: PostgreSQL via psycopg. Additional engines get
  their own file under `adapters/`, not conditionals inside agent code.

## Current status

- [x] Repo scaffolded, `pyproject.toml`, dependencies installed
- [x] `GraphState` implemented and tested (`tests/test_state.py`)
- [ ] Schema metadata layer — `adapters/postgres.py:introspect_schema()`
- [ ] `agents/schema_discovery.py`
- [ ] `agents/disambiguation.py`
- [ ] `agents/generation.py` + `safety/validator.py`
- [ ] `agents/execution.py` + `orchestrator/graph.py` (wires everything)
- [ ] `api/main.py` — POST /query, POST /query/{session_id}/clarify
- [ ] Observability (OpenTelemetry) + eval harness
- [ ] Containerize, deploy

Work through these in order — later steps assume earlier ones exist and
are tested. Run `pytest tests/ -v` before considering any step done.

## Conventions

- Every new field on `GraphState` should be added deliberately, not as a
  workaround inside one agent — it's the contract for the whole system.
- `model_config = {"extra": "forbid"}` on `GraphState` is intentional:
  typo'd fields should fail loudly, not vanish silently.
- No agent talks to the database directly except through `adapters/` —
  keeps engine-specific code out of agent logic.
