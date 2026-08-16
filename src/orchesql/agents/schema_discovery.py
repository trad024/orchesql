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


def _singularize(word: str) -> str:
    # ponytail: naive trailing-s strip, not real lemmatization -- good enough
    # to match "product" against "products"/"product_id" without a NLP dep
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokenize(text: str) -> set[str]:
    raw = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return {_singularize(w) for w in raw}


# A table's own name matching is a much stronger signal than one of its
# columns matching -- otherwise a table ties with anything that merely has
# a foreign key column referencing it (e.g. "customers" tying with "orders"
# because orders has a customer_id column).
_TABLE_NAME_WEIGHT = 3
_COLUMN_NAME_WEIGHT = 1


def _find_seed_tables(
    question: str, tables: list[SchemaTable]
) -> list[tuple[str, float]]:
    """Return (table_name, score) for tables whose name or column names
    overlap with tokens in the question. Sorted by score descending."""
    q_tokens = _tokenize(question)
    scored: list[tuple[str, float]] = []
    for t in tables:
        t_tokens = _tokenize(t.name)
        col_tokens: set[str] = set()
        for c in t.columns:
            col_tokens |= _tokenize(c.name)
        # Fraction of the table's own name matched, not raw token count --
        # otherwise a compound name like "order_items" gets full table-name
        # credit for matching just "order", tying with the actual "orders"
        # table whose entire (one-word) name matched.
        name_match_frac = len(q_tokens & t_tokens) / len(t_tokens) if t_tokens else 0
        hits = _TABLE_NAME_WEIGHT * name_match_frac + _COLUMN_NAME_WEIGHT * len(
            q_tokens & col_tokens
        )
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
    # Tables that tie but are directly FK-connected aren't a genuine
    # ambiguity -- that's a join spanning both (e.g. "customer" + "orders"
    # in one question), and the pruned schema below already includes both
    # via BFS regardless of whether we flag it. Only ask when the tied
    # tables are otherwise unrelated.
    tied_are_connected = len(tied) > 1 and all(
        any(other in fk_graph.get(name, set()) for other in tied if other != name)
        for name in tied
    )
    ambiguities = tied if len(tied) > 1 and not tied_are_connected else []

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
