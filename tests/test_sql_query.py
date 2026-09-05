"""
Tests the sql_query tool against the real database (marked db). This
version of the tool has no application-level guardrails yet (roadmap step
2, minimal loop) -- these tests deliberately prove the agent_readonly role
itself is the real safety net at this stage, not an assumption.
"""
import pytest

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
    # No SELECT-only parsing exists yet at this step -- this must be blocked
    # by the database role's own privileges (db/schema.sql's agent_readonly),
    # not by application code.
    result = run_sql_query("DELETE FROM orders WHERE 1=1")
    assert "error" in result
    assert "permission denied" in result["error"].lower()
