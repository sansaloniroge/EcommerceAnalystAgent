from __future__ import annotations

from typing import Any

from openai.types.chat import ChatCompletionFunctionToolParam

from app.db import connect_readonly

# Minimal version for the roadmap's step 2 (bare tool-calling loop). The
# agent_readonly role (db/schema.sql) already rejects any non-SELECT
# statement at the database level -- real protection, not just an
# assumption. Step 3 adds application-level guardrails on top of that
# (SELECT-only parsing, keyword blacklist, LIMIT, timeout) as defense in
# depth, plus tests that try to break them.

TOOL_SCHEMA: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "sql_query",
        "description": (
            "Execute a read-only SQL query against the Olist e-commerce Postgres database "
            "and return the resulting rows. Only SELECT statements are allowed -- the "
            "database connection itself has no write permissions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SQL SELECT statement.",
                },
            },
            "required": ["query"],
        },
    },
}


def run_sql_query(query: str) -> dict[str, Any]:
    """
    Executes `query` against the real database via the read-only role.
    Never raises -- returns {"error": ...} so the agent loop can feed the
    failure back to the model instead of crashing the whole request.
    """
    try:
        with connect_readonly() as conn, conn.cursor() as cur:
            cur.execute(query)
            columns = [desc.name for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
    except Exception as e:
        return {"error": str(e)}
