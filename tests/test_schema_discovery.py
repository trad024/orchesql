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
