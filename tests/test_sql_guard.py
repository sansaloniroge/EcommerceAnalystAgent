"""
Unit tests for the application-level SQL guardrails (roadmap step 3) --
no DB needed, these test the regex-based checks in isolation. See
tests/test_sql_query.py for the same guardrails exercised against the
real database.
"""
import pytest

from app.tools.sql_guard import MAX_ROW_LIMIT, check_query, ensure_row_limit


def test_check_query_allows_a_plain_select():
    assert check_query("SELECT * FROM orders") is None


def test_check_query_allows_a_cte():
    assert check_query("WITH x AS (SELECT 1) SELECT * FROM x") is None


def test_check_query_rejects_empty_query():
    assert check_query("") is not None
    assert check_query("   ") is not None


def test_check_query_rejects_a_query_not_starting_with_select_or_with():
    error = check_query("EXPLAIN SELECT * FROM orders")
    assert error is not None


def test_check_query_rejects_stacked_statements():
    error = check_query("SELECT 1; DROP TABLE orders")
    assert error is not None


def test_check_query_allows_a_single_trailing_semicolon():
    assert check_query("SELECT * FROM orders;") is None


def test_check_query_allows_a_semicolon_inside_a_string_literal():
    # A literal value containing ';' isn't a second statement.
    assert check_query("SELECT * FROM orders WHERE note = 'a;b'") is None


def test_check_query_ignores_keywords_inside_a_comment():
    assert check_query("SELECT * FROM orders -- please don't delete this table") is None


def test_check_query_ignores_keywords_inside_a_string_literal():
    assert check_query("SELECT * FROM orders WHERE status = 'delete_requested'") is None


def test_check_query_rejects_a_data_modifying_cte():
    # A CTE can hide a write behind a SELECT-shaped outer query.
    error = check_query("WITH x AS (DELETE FROM orders RETURNING id) SELECT * FROM x")
    assert error is not None


def test_check_query_rejects_select_into():
    error = check_query("SELECT * INTO stolen_table FROM orders")
    assert error is not None


@pytest.mark.parametrize(
    "keyword,query",
    [
        ("INSERT", "SELECT 1; INSERT INTO orders VALUES (1)"),
        ("UPDATE", "SELECT 1; UPDATE orders SET status = 'x'"),
        ("DELETE", "DELETE FROM orders"),
        ("DROP", "DROP TABLE orders"),
        ("ALTER", "ALTER TABLE orders DROP COLUMN id"),
        ("TRUNCATE", "TRUNCATE orders"),
        ("GRANT", "GRANT ALL ON orders TO public"),
        ("CREATE", "CREATE TABLE evil (id int)"),
        ("EXECUTE", "EXECUTE some_prepared_statement"),
        ("CALL", "CALL some_procedure()"),
        ("COPY", "COPY orders TO '/tmp/x.csv'"),
        ("VACUUM", "VACUUM orders"),
        ("SET", "SET statement_timeout = 0"),
    ],
)
def test_check_query_rejects_each_blocked_keyword(keyword, query):
    error = check_query(query)
    assert error is not None, f"expected {keyword!r} to be rejected in {query!r}"


def test_check_query_is_case_insensitive():
    error = check_query("select 1; drop table orders")
    assert error is not None


def test_check_query_does_not_reject_offset_as_a_hidden_set():
    # Word-boundary matching must not treat "OFFSET" as containing "SET".
    assert check_query("SELECT * FROM orders OFFSET 5") is None


def test_ensure_row_limit_appends_limit_when_missing():
    result = ensure_row_limit("SELECT * FROM orders")
    assert result == f"SELECT * FROM orders LIMIT {MAX_ROW_LIMIT}"


def test_ensure_row_limit_strips_trailing_semicolon_before_appending():
    result = ensure_row_limit("SELECT * FROM orders;")
    assert result == f"SELECT * FROM orders LIMIT {MAX_ROW_LIMIT}"


def test_ensure_row_limit_leaves_an_existing_limit_alone():
    query = "SELECT * FROM orders LIMIT 10"
    assert ensure_row_limit(query) == query


def test_ensure_row_limit_is_case_insensitive_for_existing_limit():
    query = "SELECT * FROM orders limit 10"
    assert ensure_row_limit(query) == query
