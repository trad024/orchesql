from orchesql.agents.schema_discovery import discover, _build_fk_graph, _find_seed_tables
from orchesql.orchestrator.state import ForeignKey, SchemaColumn, SchemaTable


def _sample_schema():
    return [
        SchemaTable(
            name="orders",
            columns=[
                SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                SchemaColumn(name="customer_id", data_type="integer"),
                SchemaColumn(name="total", data_type="numeric"),
            ],
            foreign_keys=[
                ForeignKey(column="customer_id", references_table="customers", references_column="id"),
            ],
        ),
        SchemaTable(
            name="customers",
            columns=[
                SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                SchemaColumn(name="name", data_type="text"),
            ],
        ),
        SchemaTable(
            name="products",
            columns=[
                SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                SchemaColumn(name="name", data_type="text"),
                SchemaColumn(name="price", data_type="numeric"),
            ],
        ),
    ]


def test_fk_graph_is_bidirectional():
    graph = _build_fk_graph(_sample_schema())
    assert "customers" in graph["orders"]
    assert "orders" in graph["customers"]


def test_seed_tables_found_by_keyword():
    seeds = _find_seed_tables("How many orders were placed?", _sample_schema())
    names = [name for name, _ in seeds]
    assert "orders" in names


def test_discover_expands_via_fk():
    ctx = discover("How many orders were placed?", _sample_schema())
    table_names = {t.name for t in ctx.tables}
    assert "orders" in table_names
    assert "customers" in table_names


def test_discover_no_match_returns_low_confidence():
    ctx = discover("something completely unrelated xyz", _sample_schema())
    assert ctx.confidence == 0.0
    assert ctx.tables == []


def test_seed_matching_handles_singular_plural():
    # "product" (question, singular) must match the "products" table (plural
    # name) at least as well as a bridging table whose FK column merely
    # contains the literal substring "product_id" -- otherwise the actual
    # subject table loses the tie-break to whatever references it.
    schema = _sample_schema() + [
        SchemaTable(
            name="order_items",
            columns=[
                SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                SchemaColumn(name="order_id", data_type="integer"),
                SchemaColumn(name="product_id", data_type="integer"),
            ],
        )
    ]
    seeds = _find_seed_tables("List all product names.", schema)
    scores = dict(seeds)
    assert scores.get("products", 0) >= scores.get("order_items", 0)
    assert "products" in [name for name, score in seeds if score == max(scores.values())]


def test_tied_but_fk_connected_tables_are_not_flagged_ambiguous():
    # customers and orders tying is a join question spanning both, not a
    # genuine ambiguity -- the pruned schema includes both via BFS either
    # way, so asking the user to pick one would be pointless friction.
    schema = [
        SchemaTable(
            name="customers",
            columns=[
                SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                SchemaColumn(name="name", data_type="text"),
            ],
        ),
        SchemaTable(
            name="orders",
            columns=[
                SchemaColumn(name="id", data_type="integer", is_primary_key=True),
                SchemaColumn(name="cust_ref", data_type="integer"),
                SchemaColumn(name="total", data_type="numeric"),
            ],
            foreign_keys=[
                ForeignKey(column="cust_ref", references_table="customers", references_column="id"),
            ],
        ),
    ]
    ctx = discover("customer orders", schema)
    assert ctx.candidate_ambiguities == []


def test_tied_unrelated_tables_are_still_flagged_ambiguous():
    # Two tables that both plausibly match but aren't FK-connected is a
    # real ambiguity -- the system should still ask rather than guess.
    schema = [
        SchemaTable(name="products", columns=[SchemaColumn(name="name", data_type="text")]),
        SchemaTable(name="categories", columns=[SchemaColumn(name="name", data_type="text")]),
    ]
    ctx = discover("show name", schema)
    assert set(ctx.candidate_ambiguities) == {"products", "categories"}
