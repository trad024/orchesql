"""Schema discovery agent — deterministic FK-graph BFS, no LLM call.

Given a full schema (list[SchemaTable]) and a natural-language question,
finds seed tables by keyword matching on table/column names, then expands
outward through foreign-key edges via BFS to build a pruned schema subset.
"""

from __future__ import annotations

import re
from collections import deque

from orchesql.orchestrator.state import (
    GraphState,
    SchemaContext,
    SchemaTable,
    Status,
)

_CONFIDENCE_HIGH = 0.85
_MAX_BFS_DEPTH = 3


def _build_fk_graph(tables: list[SchemaTable]) -> dict[str, set[str]]:
    """Adjacency list: table -> set of tables it references or is referenced by."""
    graph: dict[str, set[str]] = {t.name: set() for t in tables}
    for t in tables:
        for fk in t.foreign_keys:
            graph[t.name].add(fk.references_table)
            if fk.references_table in graph:
                graph[fk.references_table].add(t.name)
    return graph


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9]*", text.lower()))


def _find_seed_tables(
    question: str, tables: list[SchemaTable]
) -> list[tuple[str, int]]:
    """Return (table_name, match_count) for tables whose name or column names
    overlap with tokens in the question. Sorted by match count descending."""
    q_tokens = _tokenize(question)
    scored: list[tuple[str, int]] = []
    for t in tables:
        t_tokens = _tokenize(t.name)
        col_tokens: set[str] = set()
        for c in t.columns:
            col_tokens |= _tokenize(c.name)
        hits = len(q_tokens & (t_tokens | col_tokens))
        if hits:
            scored.append((t.name, hits))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _bfs_expand(
    seeds: list[str],
    fk_graph: dict[str, set[str]],
    max_depth: int = _MAX_BFS_DEPTH,
) -> set[str]:
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
    while queue:
        node, depth = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        if depth < max_depth:
            for neighbor in fk_graph.get(node, set()):
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
    return visited


def discover(
    question: str, full_schema: list[SchemaTable], pinned_table: str | None = None
) -> SchemaContext:
    """Pure function: question + full schema -> pruned SchemaContext.

    pinned_table: when the user has already resolved an ambiguity via
    disambiguation, skip re-scoring and expand from that table alone.
    """
    table_map = {t.name: t for t in full_schema}
    fk_graph = _build_fk_graph(full_schema)

    if pinned_table and pinned_table in table_map:
        expanded = _bfs_expand([pinned_table], fk_graph)
        pruned = [table_map[n] for n in expanded if n in table_map]
        return SchemaContext(tables=pruned, confidence=1.0, candidate_ambiguities=[])

    seeds = _find_seed_tables(question, full_schema)

    if not seeds:
        return SchemaContext(
            tables=[],
            confidence=0.0,
            candidate_ambiguities=[t.name for t in full_schema[:10]],
        )

    top_score = seeds[0][1]
    tied = [name for name, score in seeds if score == top_score]
    ambiguities = tied if len(tied) > 1 else []

    seed_names = [name for name, _ in seeds[:5]]
    expanded = _bfs_expand(seed_names, fk_graph)
    pruned = [table_map[n] for n in expanded if n in table_map]

    confidence = min(1.0, top_score / max(len(_tokenize(question)), 1))
    if ambiguities:
        confidence *= 0.6

    return SchemaContext(
        tables=pruned,
        confidence=round(confidence, 2),
        candidate_ambiguities=ambiguities,
    )


def run(state: GraphState, full_schema: list[SchemaTable]) -> GraphState:
    """Orchestrator node: updates state with discovered schema context."""
    ctx = discover(state.question, full_schema, pinned_table=state.clarification_response)
    state.schema_context = ctx

    if ctx.confidence < _CONFIDENCE_HIGH and ctx.candidate_ambiguities:
        state.status = Status.NEEDS_CLARIFICATION
    else:
        state.status = Status.NEEDS_GENERATION

    return state
