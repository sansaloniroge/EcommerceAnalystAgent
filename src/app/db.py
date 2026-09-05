from __future__ import annotations

import os

import psycopg

# 5s statement timeout: an LLM-generated query can accidentally be an
# expensive cross join, and this loop has no human watching it run.
STATEMENT_TIMEOUT_MS = 5_000


def agent_db_url() -> str:
    url = os.getenv("AGENT_DB_URL")
    if not url:
        raise RuntimeError("AGENT_DB_URL is required (see .env.example)")
    return url


def connect_readonly() -> psycopg.Connection:
    """
    Connects as agent_readonly (SELECT-only at the database level -- see
    db/schema.sql). This is the connection the sql_query tool uses to run
    LLM-generated SQL; nothing in this codebase should use it for writes.
    """
    return psycopg.connect(agent_db_url(), options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}")
