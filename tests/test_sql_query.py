"""
Tests the sql_query tool against the real database (marked db). Unit-level
guardrail behavior (blacklist, stacked statements, LIMIT injection) is
covered in isolation in tests/test_sql_guard.py -- these tests exercise the
real tool end to end, including the case where the application-level guard
and the database role's own privileges would both block the same attack.
"""
import pytest

from app.tools.sql_guard import MAX_ROW_LIMIT
from app.tools.sql_query import run_sql_query

pytestmark = pytest.mark.db


def test_run_sql_query_returns_rows_for_a_real_select():
    result = run_sql_query("SELECT count(*) AS n FROM orders")
    assert "error" not in result
    assert result["columns"] == ["n"]
    assert result["rows"][0][0] == 99441


def test_run_sql_query_returns_error_for_invalid_sql_instead_of_raising():
    result = run_sql_query("SELECT this is not valid sql")
    assert "error" in result


def test_run_sql_query_is_rejected_by_the_readonly_role_for_a_write():
    # Bypass the application-level guard directly to prove the DB role is
    # still a real second line of defense, not just an assumption -- the
    # guard alone shouldn't be the only thing standing between the model
    # and a write.
    from app.tools.sql_query import connect_readonly

    with connect_readonly() as conn, conn.cursor() as cur:
        with pytest.raises(Exception) as exc_info:
            cur.execute("DELETE FROM orders WHERE 1=1")
    assert "permission denied" in str(exc_info.value).lower()


def test_run_sql_query_rejects_a_stacked_drop_before_reaching_the_database():
    result = run_sql_query("SELECT 1; DROP TABLE orders")
    assert "error" in result
    assert "permission denied" not in result["error"].lower()


def test_run_sql_query_rejects_a_data_modifying_cte():
    result = run_sql_query("WITH x AS (DELETE FROM orders RETURNING id) SELECT * FROM x")
    assert "error" in result


def test_run_sql_query_caps_row_count_when_no_limit_is_given():
    result = run_sql_query("SELECT * FROM order_items")
    assert "error" not in result
    assert result["row_count"] <= MAX_ROW_LIMIT


def test_run_sql_query_still_works_with_an_explicit_smaller_limit():
    result = run_sql_query("SELECT * FROM orders LIMIT 5")
    assert "error" not in result
    assert result["row_count"] == 5
