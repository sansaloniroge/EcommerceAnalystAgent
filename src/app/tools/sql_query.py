from __future__ import annotations

from typing import Any

from openai.types.chat import ChatCompletionFunctionToolParam

from app.db import connect_readonly
from app.tools.sql_guard import check_query, ensure_row_limit

# The agent_readonly role (db/schema.sql) rejects any non-SELECT statement
# at the database level -- real protection, not just an assumption.
# check_query/ensure_row_limit (roadmap step 3) add application-level
# guardrails on top of that (SELECT-only parsing, keyword blacklist, row
# limit; the statement timeout lives in db.connect_readonly) as defense in
# depth, so a bad query is caught before it ever reaches Postgres.

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
    error = check_query(query)
    if error:
        return {"error": error}
    query = ensure_row_limit(query)

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
