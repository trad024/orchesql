"""Eval harness -- execution-accuracy check for the orchestrator loop.

For each (question, expected_sql) case: runs the question through the
real graph (schema_discovery -> generation -> validator -> execution)
against a live DB + LLM, then executes expected_sql separately and
compares result sets. Execution-accuracy rather than exact-SQL-match,
since two different queries can correctly answer the same question.

Requires DATABASE_URL and GROQ_API_KEY. Run with:
    python -m orchesql.eval.harness
"""

from __future__ import annotations

import os
import sys

from orchesql.adapters.postgres import execute_query, introspect_schema
from orchesql.orchestrator.graph import build_graph
from orchesql.orchestrator.state import GraphState

CASES = [
    ("How many customers are there?", "SELECT COUNT(*) FROM customers"),
    ("What is the total revenue from all orders?", "SELECT SUM(total) FROM orders"),
    ("List all product names.", "SELECT name FROM products"),
    (
        "For each customer, show their name and how many orders they placed.",
        "SELECT c.name, COUNT(o.id) FROM customers c "
        "LEFT JOIN orders o ON o.customer_id = c.id GROUP BY c.name",
    ),
    ("What is the price of the Widget?", "SELECT price FROM products WHERE name = 'Widget'"),
]


def _normalize(rows: list[list]) -> set[tuple]:
    return {tuple(r) for r in rows}


def run_eval(connection_string: str, llm_call) -> tuple[int, int]:
    schema = introspect_schema(connection_string)
    graph = build_graph(schema, connection_string, llm_call)

    passed = 0
    for i, (question, expected_sql) in enumerate(CASES, 1):
        state = GraphState(question=question)
        config = {"configurable": {"thread_id": f"eval-{i}"}}
        result = graph.invoke(state, config=config)

        if "__interrupt__" in result or result["status"] != "done":
            print(f"[FAIL] {question!r} -> status={result['status']}")
            continue

        generated_sql = result["generated_sql"]
        try:
            expected = execute_query(connection_string, expected_sql)
        except Exception as e:
            print(f"[FAIL] {question!r} -> expected_sql execution error: {e}")
            continue

        actual_rows = _normalize(result["results"].rows)
        expected_rows = _normalize(expected["rows"])

        if actual_rows == expected_rows:
            print(f"[PASS] {question!r} -> {generated_sql}")
            passed += 1
        else:
            print(
                f"[FAIL] {question!r}\n"
                f"  generated: {generated_sql} -> {actual_rows}\n"
                f"  expected:  {expected_sql} -> {expected_rows}"
            )

    return passed, len(CASES)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    conn_str = os.getenv("DATABASE_URL")
    if not conn_str:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    from orchesql.api.main import _get_llm_call

    passed, total = run_eval(conn_str, _get_llm_call())
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)
