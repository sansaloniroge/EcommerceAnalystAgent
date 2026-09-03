"""
Tests against a real running Postgres (docker compose up). Marked `db` --
skipped by default; run explicitly with `pytest -m db` once the container
is up (see Makefile `make up`).
"""
import os

import psycopg
import pytest

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "customers",
    "sellers",
    "products",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
    "product_category_name_translation",
}


def _connect(url_env_var: str) -> psycopg.Connection:
    url = os.getenv(url_env_var)
    if not url:
        pytest.skip(f"{url_env_var} not set (see .env.example)")
    return psycopg.connect(url)


def test_all_scoped_tables_exist():
    with _connect("DATABASE_URL") as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = {row[0] for row in cur.fetchall()}
    assert EXPECTED_TABLES <= tables


def test_agent_readonly_can_select():
    with _connect("AGENT_DB_URL") as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM orders")
        cur.fetchone()  # must not raise


def test_agent_readonly_cannot_write():
    with _connect("AGENT_DB_URL") as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("INSERT INTO customers (customer_id, customer_unique_id) VALUES ('x', 'y')")
        conn.rollback()
