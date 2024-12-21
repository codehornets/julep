from typing import Literal
from uuid import UUID

import asyncpg
from beartype import beartype
from fastapi import HTTPException
from litellm.utils import _select_tokenizer as select_tokenizer
from uuid_extensions import uuid7

from ...autogen.openapi_model import CreateEntryRequest, Entry, Relation
from ...common.utils.datetime import utcnow
from ...common.utils.messages import content_to_json
from ...metrics.counters import increase_counter
from ..utils import partialclass, pg_query, rewrap_exceptions, wrap_in_class

# Query for checking if the session exists
session_exists_query = """
SELECT EXISTS (
    SELECT 1 FROM sessions
    WHERE session_id = $1 AND developer_id = $2
) AS exists;
"""

# Define the raw SQL query for creating entries
entry_query = """
INSERT INTO entries (
    session_id,
    entry_id, 
    source,
    role,
    event_type,
    name,
    content,
    tool_call_id,
    tool_calls,
    model,
    token_count,
    tokenizer,
    created_at,
    timestamp
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
RETURNING *;
"""

# Define the raw SQL query for creating entry relations
entry_relation_query = """
INSERT INTO entry_relations (
    session_id,
    head,
    relation,
    tail,
) VALUES ($1, $2, $3, $4, $5)
RETURNING *;
"""


@rewrap_exceptions(
    {
        asyncpg.ForeignKeyViolationError: partialclass(
            HTTPException,
            status_code=404,
            detail="Session not found",
        ),
        asyncpg.UniqueViolationError: partialclass(
            HTTPException,
            status_code=409,
            detail="Entry already exists",
        ),
        asyncpg.NotNullViolationError: partialclass(
            HTTPException,
            status_code=400,
            detail="Not null violation",
        ),
        asyncpg.NoDataFoundError: partialclass(
            HTTPException,
            status_code=404,
            detail="Session not found",
        ),
    }
)
@wrap_in_class(
    Entry,
    transform=lambda d: {
        "id": d.pop("entry_id"),
        **d,
    },
)
@increase_counter("create_entries")
@pg_query
@beartype
async def create_entries(
    *,
    developer_id: UUID,
    session_id: UUID,
    data: list[CreateEntryRequest],
) -> list[tuple[str, list, Literal["fetch", "fetchmany", "fetchrow"]]]:
    # Convert the data to a list of dictionaries
    data_dicts = [item.model_dump(mode="json") for item in data]

    # Prepare the parameters for the query
    params = []

    for item in data_dicts:
        params.append(
            [
                session_id,  # $1
                item.pop("id", None) or uuid7(),  # $2
                item.get("source"),  # $3
                item.get("role"),  # $4
                item.get("event_type") or "message.create",  # $5
                item.get("name"),  # $6
                content_to_json(item.get("content") or {}),  # $7
                item.get("tool_call_id"),  # $8
                content_to_json(item.get("tool_calls") or {}),  # $9
                item.get("model"),  # $10
                item.get("token_count"),  # $11
                select_tokenizer(item.get("model"))["type"],  # $12
                item.get("created_at") or utcnow(),  # $13
                utcnow().timestamp(),  # $14
            ]
        )

    return [
        (
            session_exists_query,
            [session_id, developer_id],
            "fetchrow",
        ),
        (
            entry_query,
            params,
            "fetchmany",
        ),
    ]


@rewrap_exceptions(
    {
        asyncpg.ForeignKeyViolationError: partialclass(
            HTTPException,
            status_code=404,
            detail="Session not found",
        ),
        asyncpg.UniqueViolationError: partialclass(
            HTTPException,
            status_code=409,
            detail="Entry already exists",
        ),
        asyncpg.NoDataFoundError: partialclass(
            HTTPException,
            status_code=404,
            detail="Session not found",
        ),
    }
)
@wrap_in_class(Relation)
@increase_counter("add_entry_relations")
@pg_query
@beartype
async def add_entry_relations(
    *,
    developer_id: UUID,
    session_id: UUID,
    data: list[Relation],
) -> list[tuple[str, list, Literal["fetch", "fetchmany", "fetchrow"]]]:
    # Convert the data to a list of dictionaries
    data_dicts = [item.model_dump(mode="json") for item in data]

    # Prepare the parameters for the query
    params = []

    for item in data_dicts:
        params.append(
            [
                item.get("session_id"),  # $1
                item.get("head"),  # $2
                item.get("relation"),  # $3
                item.get("tail"),  # $4
            ]
        )

    return [
        (
            session_exists_query,
            [session_id, developer_id],
            "fetchrow",
        ),
        (
            entry_relation_query,
            params,
            "fetchmany",
        ),
    ]
