from orchesql.safety.validator import validate
from orchesql.orchestrator.state import SchemaContext, SchemaTable, SchemaColumn


def test_valid_select_passes():
    assert validate("SELECT 1") == []


def test_insert_blocked():
    errors = validate("INSERT INTO foo VALUES (1)")
    assert any("Forbidden" in e for e in errors)


def test_delete_blocked():
    errors = validate("DELETE FROM foo")
    assert any("Forbidden" in e for e in errors)


def test_drop_blocked():
    errors = validate("DROP TABLE foo")
    assert any("Forbidden" in e for e in errors)


def test_recursive_cte_blocked():
    sql = "WITH RECURSIVE cte AS (SELECT 1 UNION ALL SELECT 1) SELECT * FROM cte"
    errors = validate(sql)
    assert any("Recursive" in e for e in errors)


def test_unknown_table_caught():
    ctx = SchemaContext(
        tables=[SchemaTable(name="orders", columns=[SchemaColumn(name="id", data_type="int")])],
        confidence=1.0,
    )
    errors = validate("SELECT * FROM nonexistent", ctx)
    assert any("Unknown table" in e for e in errors)


def test_known_table_passes():
    ctx = SchemaContext(
        tables=[SchemaTable(name="orders", columns=[SchemaColumn(name="id", data_type="int")])],
        confidence=1.0,
    )
    errors = validate("SELECT id FROM orders", ctx)
    assert errors == []


def test_parse_error():
    errors = validate("SELEC GIBBERISH ???")
    assert len(errors) > 0
