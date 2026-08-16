# OrcheSQL

Multi-agent orchestration that turns natural-language questions into SQL
against large, real production databases (200+ tables) — without ever
routing a single row of data through an LLM.

**Helm** (in [`web/`](web/)) is the reference web console for it.

## Why this exists

Stuffing an entire schema into one prompt works for a dozen tables. At
production scale it doesn't: the schema alone can blow the context window,
the model loses track of what's actually relevant, and accuracy collapses.
Most demo-grade NL-to-SQL systems also either leak row-level data to the LLM
directly, or answer genuinely ambiguous questions with a confident guess
instead of asking.

OrcheSQL is built around one non-negotiable constraint instead:

> **The LLM only ever sees schema metadata** — table names, column names,
> types, foreign-key relationships, and the question itself. It never sees a
> row of real data. Raw data stays inside your own environment at all times;
> only the generated SQL and its execution ever touch it.

## How it works

A central orchestrator — a [LangGraph](https://github.com/langchain-ai/langgraph)
`StateGraph` — holds one shared, typed state object (`GraphState`) and
decides which agent runs next purely by reading its `status` field after
each step. This is what lets it pause mid-flow to ask a clarifying question
instead of being locked into a linear pipeline.

| Agent | LLM? | What it does |
|---|---|---|
| `schema_discovery` | no | Deterministic. Resolves seed tables from keyword matches in the question, then expands through a pre-built foreign-key graph via BFS. Returns a pruned schema subset + confidence score. |
| `disambiguation` | yes (phrasing only) | Triggers on low confidence or tied table matches. Uses LangGraph's `interrupt()` to pause the graph and surface a multiple-choice clarifying question, then resumes from that exact point via `Command(resume=...)` once answered. |
| `generation` | yes | MAC-SQL-style decomposition: reasons through the question before producing SQL, using only the pruned schema. Returns SQL + a one-sentence explanation from a single call. |
| safety validator | no | Parses every candidate query with `sqlglot` into an AST before it's ever treated as executable: SELECT-only, no DML/DDL, no recursive CTEs, every referenced table/column cross-checked against the schema to catch hallucinations. |
| `execution` | no | Runs only already-validated SQL, in a read-only transaction with a statement timeout and a row cap. The only component holding a live database connection. |

Execution and validation failures loop back to `generation`, bounded by
`max_retries`, with every failed attempt (and why it failed) kept in state
so a retry has real context instead of blindly resubmitting.

Every node, plus the request itself, emits an [OpenTelemetry](https://opentelemetry.io/)
span, so a single request renders as one correlated trace.

## Project layout

```
orchesql/
├── src/orchesql/
│   ├── orchestrator/   GraphState, graph assembly, tracing
│   ├── agents/         schema_discovery, disambiguation, generation, execution
│   ├── adapters/       per-engine DB drivers (postgres.py)
│   ├── safety/         sqlglot-based AST validator
│   ├── eval/           execution-accuracy eval harness
│   └── api/            FastAPI app
├── tests/              pytest unit + integration tests
├── db/init.sql          sample schema + seed data for local dev
├── web/                 Helm — the Next.js web console
├── docker-compose.yml
└── Dockerfile
```

## Requirements

- **Python 3.11+**
- **Docker** and Docker Compose (recommended path — see below), *or* a local
  PostgreSQL instance
- **Node.js 18+** and [pnpm](https://pnpm.io/) — only if you're running the
  web console
- A **[Groq](https://console.groq.com/keys) API key** — the only supported
  LLM provider (used via Groq's OpenAI-compatible endpoint)

## Running it

### Option A — Docker Compose (recommended)

This runs Postgres and the API together, with a small seeded sample schema
(`customers`, `products`, `orders`, `order_items`) so there's something real
to query immediately.

1. Create a `.env` file in the repo root:

   ```
   DATABASE_URL=postgresql://orchesql:orchesql@localhost:5432/orchesql
   GROQ_API_KEY=your-groq-api-key
   ORCHESQL_MODEL=llama-3.3-70b-versatile
   ```

2. Start it:

   ```bash
   docker compose up -d --build
   ```

3. Confirm it's up:

   ```bash
   curl http://localhost:8000/health
   ```

4. Ask it something:

   ```bash
   curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"question": "How many orders has each customer placed?"}'
   ```

Tear down with `docker compose down`.

### Option B — run the API on the host

Useful for development/debugging without rebuilding a container each time.

```bash
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
```

You still need a Postgres instance reachable at `DATABASE_URL` — either
`docker compose up -d db` (just the database) or your own instance. Then:

```bash
uvicorn orchesql.api.main:app --reload --port 8000
```

Environment variables are loaded from `.env` automatically (via
`python-dotenv`).

### Running the web console (Helm)

```bash
cd web
pnpm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at the API if not on localhost:8000
pnpm dev
```

Open `http://localhost:3000`. It talks to the API directly from the browser,
so the API must be running and reachable, and the API's CORS origin must
include the console's origin (see `ORCHESQL_CORS_ORIGINS` below).

## Configuration reference

All read from the environment (or `.env` in the repo root).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Postgres connection string. Schema is introspected once at startup and cached — no per-request DB call for schema discovery. |
| `GROQ_API_KEY` | yes | — | Groq API key, used for `generation` and `disambiguation`. |
| `ORCHESQL_MODEL` | no | `llama-3.3-70b-versatile` | Groq model id. |
| `ORCHESQL_CORS_ORIGINS` | no | `http://localhost:3000` | Comma-separated list of origins allowed to call the API from a browser. |
| `NEXT_PUBLIC_API_URL` *(web only)* | no | `http://localhost:8000` | API base URL the web console calls. |

If `DATABASE_URL` is unreachable at startup, the API stays up in degraded
mode (logs a warning, `/health` still responds) rather than crashing —
queries will fail until Postgres is reachable.

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check. |
| `POST /query` | Body: `{"question": "..."}`. Returns either a result (`status: "done"`, with `sql`, `explanation`, `results`) or a clarification request (`status: "needs_clarification"`, with `clarification.question` and `.options`). |
| `POST /query/{session_id}/clarify` | Body: `{"answer": "..."}`. Resumes a paused session with the user's answer to a clarification request; returns the same response shape as `/query`. |

## Testing

```bash
pytest tests/ -v
```

Unit and integration tests use fakes/mocks for the LLM and DB — no live
services required. One test (`test_graph.py`) exercises the full
`interrupt()` → `Command(resume=...)` → execution loop against a mocked DB
call.

## Evaluating accuracy

```bash
python -m orchesql.eval.harness
```

Runs a small set of question → expected-SQL cases through the real graph
against a **live** DB + LLM (needs `DATABASE_URL` and `GROQ_API_KEY`), then
compares **execution results** rather than SQL text — a differently-worded
but correct query still passes. Prints a pass/fail per case and exits
non-zero on any failure, so it's usable as a CI gate.

## Design notes / prior art

- **[MAC-SQL](https://arxiv.org/abs/2312.11242)** — closest architectural
  precedent (Selector/Decomposer/Refiner split). Borrowed: decomposition-based
  generation and the refiner/retry loop. Its documented DoS vulnerability via
  unbounded recursive CTEs directly shaped the safety validator here — that
  gate exists *before* execution is wired up, not after.
- **LinkAlign** — informed the schema-discovery fallback strategy, though the
  default here is deterministic FK-graph traversal rather than full semantic
  retrieval, to stay cheap and fast at 200+ tables.
- **`nadeem4/nl2sql`** — closest single-repo match: a directed cyclic graph
  in LangGraph, AST-valid-by-construction generation, sandboxed execution.
- **WrenAI** — closest production example of the "schema/semantic layer only,
  never expose rows" governance model.
- **Original contribution**: the disambiguation agent. None of the above
  treat "ask the user back" as a first-class step in the core loop.

## Status

- [x] Schema metadata layer (Postgres adapter)
- [x] Schema discovery (deterministic FK-graph BFS)
- [x] Disambiguation (interrupt/resume)
- [x] Generation + safety validator
- [x] Execution + bounded retry loop
- [x] FastAPI endpoints
- [x] OpenTelemetry tracing
- [x] Execution-accuracy eval harness
- [x] Containerized (Docker Compose)
- [x] Web console (Helm)
- [ ] Additional DB adapters beyond Postgres
- [ ] Persistent (non-in-memory) checkpointer for surviving API restarts mid-clarification
