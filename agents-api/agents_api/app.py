import os
from contextlib import asynccontextmanager
from typing import Any, Protocol

from aiobotocore.session import get_session
from fastapi import APIRouter, FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from scalar_fastapi import get_scalar_api_reference

from .clients.pg import create_db_pool
from .env import api_prefix, hostname, protocol, public_port


class Assignable(Protocol):
    def __setattr__(self, name: str, value: Any) -> None: ...


class ObjectWithState(Protocol):
    state: Assignable


# TODO: This currently doesn't use .env variables, but we should move to using them
@asynccontextmanager
async def lifespan(*containers: list[FastAPI | ObjectWithState]):
    # INIT POSTGRES #
    pg_dsn = os.environ.get("PG_DSN")

    for container in containers:
        if not getattr(container.state, "postgres_pool", None):
            container.state.postgres_pool = await create_db_pool(pg_dsn)

    # INIT S3 #
    s3_access_key = os.environ.get("S3_ACCESS_KEY")
    s3_secret_key = os.environ.get("S3_SECRET_KEY")
    s3_endpoint = os.environ.get("S3_ENDPOINT")

    for container in containers:
        if not getattr(container.state, "s3_client", None):
            session = get_session()
            container.state.s3_client = await session.create_client(
                "s3",
                aws_access_key_id=s3_access_key,
                aws_secret_access_key=s3_secret_key,
                endpoint_url=s3_endpoint,
            ).__aenter__()

    try:
        yield
    finally:
        # CLOSE POSTGRES #
        for container in containers:
            if getattr(container.state, "postgres_pool", None):
                await container.state.postgres_pool.close()
                container.state.postgres_pool = None

        # CLOSE S3 #
        for container in containers:
            if getattr(container.state, "s3_client", None):
                await container.state.s3_client.close()
                container.state.s3_client = None


app: FastAPI = FastAPI(
    docs_url="/swagger",
    openapi_prefix=api_prefix,
    redoc_url=None,
    title="Julep Agents API",
    description="API for Julep Agents",
    version="0.4.0",
    terms_of_service="https://www.julep.ai/terms",
    contact={
        "name": "Julep",
        "url": "https://www.julep.ai",
        "email": "developers@julep.ai",
    },
    root_path=api_prefix,
    lifespan=lifespan,
    #
    # Global dependencies
    # FIXME: This is blocking access to scalar
    # dependencies=[Depends(valid_content_length)],
)

# Enable metrics
Instrumentator().instrument(app).expose(app, include_in_schema=False)


# Create a new router for the docs
scalar_router = APIRouter()


@scalar_router.get("/docs", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url[1:],  # Remove leading '/'
        title=app.title,
        servers=[{"url": f"{protocol}://{hostname}:{public_port}{api_prefix}"}],
    )


# Add the docs_router without dependencies
app.include_router(scalar_router)


# content-length validation
# FIXME: This is blocking access to scalar
# NOTE: This relies on client reporting the correct content-length header
# TODO: We should use streaming for large payloads
# @app.middleware("http")
# async def validate_content_length(
#     request: Request,
#     call_next: Callable[[Request], Coroutine[Any, Any, Response]],
# ):
#     content_length = request.headers.get("content-length")

#     if not content_length:
#         return Response(status_code=411, content="Content-Length header is required")

#     if int(content_length) > max_payload_size:
#         return Response(status_code=413, content="Payload too large")

#     return await call_next(request)
