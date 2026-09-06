from __future__ import annotations

import re

# Roadmap step 3: application-level guardrails on top of the agent_readonly
# DB role (db/schema.sql), which is still the real safety net -- this is
# defense in depth, not a full SQL parser. A regex-based blacklist can't
# catch everything a real parser would (e.g. a LIMIT buried in a subquery
# hides an unbounded outer query), but it's the design's deliberate choice
# over pulling in a SQL grammar library for a read-only agent tool.

MAX_ROW_LIMIT = 1000

# Anything that isn't a plain read. INTO covers `SELECT ... INTO new_table`
# (INSERT INTO is already covered by INSERT, but SELECT INTO isn't).
_BLOCKED_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "CREATE",
    "EXECUTE",
    "EXEC",
    "CALL",
    "COPY",
    "VACUUM",
    "MERGE",
    "ATTACH",
    "DETACH",
    "LOCK",
    "SET",
    "RESET",
    "REFRESH",
    "DO",
    "INTO",
]

_ALLOWED_LEADING_KEYWORDS = {"SELECT", "WITH"}


def _mask(query: str) -> str:
    """
    Replaces the contents of comments and single-quoted string literals with
    spaces (same length, positions preserved) so the checks below don't
    false-positive on SQL text that only appears inside a comment or a
    string value -- e.g. a status column literally valued 'delete_requested',
    or a comment that happens to mention "update this later".
    """
    out: list[str] = []
    i, n = 0, len(query)
    while i < n:
        two = query[i : i + 2]
        if two == "--":
            j = query.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif two == "/*":
            j = query.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(" " * (j - i))
            i = j
        elif query[i] == "'":
            j = i + 1
            while j < n:
                if query[j] == "'":
                    if j + 1 < n and query[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(" " * (j - i))
            i = j
        else:
            out.append(query[i])
            i += 1
    return "".join(out)


def check_query(query: str) -> str | None:
    """
    Returns an error message if `query` isn't an allowed single SELECT
    statement, or None if it's safe to run.
    """
    if not query or not query.strip():
        return "Empty query."

    masked = _mask(query)

    statements = [s for s in masked.split(";") if s.strip()]
    if len(statements) > 1:
        return "Only a single SQL statement is allowed (no ';'-separated statements)."

    leading = re.match(r"\s*(\w+)", masked)
    first_word = leading.group(1).upper() if leading else ""
    if first_word not in _ALLOWED_LEADING_KEYWORDS:
        return "Only SELECT statements (optionally starting with WITH) are allowed."

    for keyword in _BLOCKED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", masked, re.IGNORECASE):
            return f"Query contains a disallowed keyword: {keyword}."

    return None


def ensure_row_limit(query: str, limit: int = MAX_ROW_LIMIT) -> str:
    """
    Appends `LIMIT {limit}` if the query has no LIMIT clause anywhere.
    Assumes `check_query` already passed (single statement).
    """
    masked = _mask(query)
    if re.search(r"\bLIMIT\b", masked, re.IGNORECASE):
        return query

    trimmed = query.rstrip()
    if trimmed.endswith(";"):
        trimmed = trimmed[:-1].rstrip()
    return f"{trimmed} LIMIT {limit}"
