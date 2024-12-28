from uuid import UUID

import asyncpg
from beartype import beartype
from fastapi import HTTPException
from sqlglot import parse_one

from ...autogen.openapi_model import PatchSessionRequest, ResourceUpdatedResponse
from ...metrics.counters import increase_counter
from ..utils import partialclass, pg_query, rewrap_exceptions, wrap_in_class

# Define the raw SQL queries
# Build dynamic SET clause based on provided fields
session_query = parse_one("""
WITH updated_session AS (
    UPDATE sessions 
    SET
        situation = COALESCE($3, situation),
        system_template = COALESCE($4, system_template),
        metadata = sessions.metadata || $5,
        render_templates = COALESCE($6, render_templates),
        token_budget = COALESCE($7, token_budget),
        context_overflow = COALESCE($8, context_overflow),
        forward_tool_calls = COALESCE($9, forward_tool_calls),
        recall_options = sessions.recall_options || $10
    WHERE 
        developer_id = $1 
        AND session_id = $2
    RETURNING *
)
SELECT * FROM updated_session;
""").sql(pretty=True)


@rewrap_exceptions(
    {
        asyncpg.ForeignKeyViolationError: partialclass(
            HTTPException,
            status_code=404,
            detail="The specified developer or session does not exist.",
        ),
        asyncpg.NoDataFoundError: partialclass(
            HTTPException,
            status_code=404,
            detail="Session not found",
        ),
        asyncpg.CheckViolationError: partialclass(
            HTTPException,
            status_code=400,
            detail="Invalid session data provided.",
        ),
    }
)
@wrap_in_class(
    ResourceUpdatedResponse,
    one=True,
    transform=lambda d: {"id": d["session_id"], "updated_at": d["updated_at"]},
)
@increase_counter("patch_session")
@pg_query
@beartype
async def patch_session(
    *,
    developer_id: UUID,
    session_id: UUID,
    data: PatchSessionRequest,
) -> list[tuple[str, list]]:
    """
    Constructs SQL queries to patch a session and its participant lookups.

    Args:
        developer_id (UUID): The developer's UUID
        session_id (UUID): The session's UUID
        data (PatchSessionRequest): Session patch data

    Returns:
        list[tuple[str, list]]: List of SQL queries and their parameters
    """

    # Extract fields from data, using None for unset fields
    session_params = [
        developer_id,  # $1
        session_id,  # $2
        data.situation,  # $3
        data.system_template,  # $4
        data.metadata or {},  # $5
        data.render_templates,  # $6
        data.token_budget,  # $7
        data.context_overflow,  # $8
        data.forward_tool_calls,  # $9
        data.recall_options.model_dump() if data.recall_options else {},  # $10
    ]

    return [(session_query, session_params)]
