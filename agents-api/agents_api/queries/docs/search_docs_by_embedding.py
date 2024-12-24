from typing import Any, List, Literal
from uuid import UUID

from beartype import beartype
from fastapi import HTTPException
import asyncpg

from ...autogen.openapi_model import DocReference
from ..utils import pg_query, rewrap_exceptions, wrap_in_class, partialclass

# Raw query for vector search
search_docs_by_embedding_query = """
SELECT * FROM search_by_vector(
    $1, -- developer_id
    $2::vector(1024), -- query_embedding
    $3::text[], -- owner_types
    $UUID_LIST::uuid[], -- owner_ids
    $4, -- k
    $5, -- confidence
    $6 -- metadata_filter
)
"""

@rewrap_exceptions(
    {
        asyncpg.UniqueViolationError: partialclass(
            HTTPException,
            status_code=404,
            detail="The specified developer does not exist.",
        )
    }
)
@wrap_in_class(
    DocReference,
    transform=lambda d: {
        "owner": {
            "id": d["owner_id"],
            "role": d["owner_type"],
        },
        "metadata": d.get("metadata", {}),
        **d,
    },
)
@pg_query
@beartype
async def search_docs_by_embedding(
    *,
    developer_id: UUID,
    query_embedding: List[float],
    k: int = 10,
    owners: list[tuple[Literal["user", "agent"], UUID]],
    confidence: float = 0.5,
    metadata_filter: dict[str, Any] = {},
) -> tuple[str, list]:
    """
    Vector-based doc search:

    Parameters:
        developer_id (UUID): The ID of the developer.
        query_embedding (List[float]): The vector to query.
        k (int): The number of results to return.
        owners (list[tuple[Literal["user", "agent"], UUID]]): List of (owner_type, owner_id) tuples.
        confidence (float): The confidence threshold for the search.
        metadata_filter (dict): Metadata filter criteria.

    Returns:
        tuple[str, list]: SQL query and parameters for searching the documents.
    """
    if k < 1:
        raise HTTPException(status_code=400, detail="k must be >= 1")

    if not query_embedding:
        raise HTTPException(status_code=400, detail="Empty embedding provided")

    # Convert query_embedding to a string
    query_embedding_str = f"[{', '.join(map(str, query_embedding))}]"

    # Extract owner types and IDs
    owner_types: list[str] = [owner[0] for owner in owners]
    owner_ids: list[str] = [str(owner[1]) for owner in owners]

    # NOTE: Manually replace uuids list coz asyncpg isnt sending it correctly
    owner_ids_pg_str = f"ARRAY['{'\', \''.join(owner_ids)}']"
    query = search_docs_by_embedding_query.replace("$UUID_LIST", owner_ids_pg_str)

    return (
        query,
        [
            developer_id,
            query_embedding_str,
            owner_types,
            k,
            confidence,
            metadata_filter,
        ],
    )
