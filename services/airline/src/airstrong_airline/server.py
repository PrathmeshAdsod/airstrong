from __future__ import annotations

import json
import os
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID

import psycopg
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from psycopg.rows import dict_row
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from .artifacts import evaluate_generated_candidates, solver_bundle, validated_candidates
from .database import (
    DbConnection,
    DbRow,
    connect,
    create_world_once,
    default_world,
    events_after,
    load_snapshot,
    load_world,
    migrate,
    persist_generated_artifact,
    persist_recovery_batch,
    reset_world,
    trigger_hero_scenario,
)
from .views import (
    aircraft_investigation,
    crew_investigation,
    data_view,
    passenger_investigation,
    public_value,
    recovery_batch_view,
    snapshot_view,
    world_view,
)

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

mcp = MCPServer(
    "Airstrong airline operations",
    instructions=(
        "Read the authoritative Aliens Airline simulation state. Tool output is factual PostgreSQL state. "
        "Do not invent flights, crew, passengers, candidate actions, metrics, or violations."
    ),
)


def _database_url() -> str:
    value = os.getenv("AIRSTRONG_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("AIRSTRONG_DATABASE_URL is required")
    return value


def initialize_database() -> UUID:
    with connect(_database_url()) as connection:
        migrate(connection)
        return default_world(connection)


def _world_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError("world_id must be a UUID") from error


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(error, KeyError):
        return JSONResponse({"error": "not_found", "detail": str(error)}, status_code=404)
    if isinstance(error, ValueError):
        return JSONResponse({"error": "invalid_request", "detail": str(error)}, status_code=409)
    return JSONResponse({"error": "service_error", "detail": str(error)}, status_code=503)


def _with_database(
    view: Callable[[DbConnection, UUID], Any],
    world_id: str,
) -> Any:
    with connect(_database_url()) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return view(connection, _world_id(world_id))


@mcp.tool(annotations=READ_ONLY)
def airline_world_snapshot(
    world_id: Annotated[str, Field(min_length=36, max_length=36)],
) -> dict[str, Any]:
    """Read the immutable source data and calculated impacts for one world revision."""
    return _with_database(snapshot_view, world_id)


@mcp.tool(annotations=READ_ONLY)
def airline_aircraft_investigation(
    world_id: Annotated[str, Field(min_length=36, max_length=36)],
) -> dict[str, Any]:
    """Read unavailable aircraft, impacted rotations, and factual substitution inventory."""
    return _with_database(aircraft_investigation, world_id)


@mcp.tool(annotations=READ_ONLY)
def airline_crew_investigation(
    world_id: Annotated[str, Field(min_length=36, max_length=36)],
) -> dict[str, Any]:
    """Read impacted crew, assignments, qualifications, and remaining stored duty windows."""
    return _with_database(crew_investigation, world_id)


@mcp.tool(annotations=READ_ONLY)
def airline_passenger_investigation(
    world_id: Annotated[str, Field(min_length=36, max_length=36)],
) -> dict[str, Any]:
    """Read impacted passenger parties and their authoritative itinerary legs."""
    return _with_database(passenger_investigation, world_id)


@mcp.tool(annotations=READ_ONLY)
def airline_recovery_candidates(
    world_id: Annotated[str, Field(min_length=36, max_length=36)],
) -> dict[str, Any]:
    """Read the latest stored candidate batch, twin results, and deterministic ranking."""
    result = _with_database(recovery_batch_view, world_id)
    return {"batch": result}


@mcp.tool(annotations=READ_ONLY)
def airline_solver_bundle() -> dict[str, Any]:
    """Return the hashed trusted solver library used by runtime-generated Daytona code."""
    return solver_bundle()


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    try:
        with connect(_database_url()) as connection:
            connection.execute("SELECT 1")
        return JSONResponse({"status": "ok"})
    except Exception as error:  # pragma: no cover - exercised by container health checks
        return _error_response(error)


@mcp.custom_route("/api/worlds/default", methods=["GET"])
async def get_default_world(_: Request) -> JSONResponse:
    try:
        with connect(_database_url()) as connection:
            world_id = default_world(connection)
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                return JSONResponse(world_view(connection, world_id))
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds", methods=["POST"])
async def post_world(request: Request) -> JSONResponse:
    try:
        idempotency_key = request.headers.get("Idempotency-Key", "")
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        display_name = str(body.get("displayName", "Aliens Airline"))
        with connect(_database_url()) as connection:
            world_id, replayed = create_world_once(
                connection,
                idempotency_key=idempotency_key,
                display_name=display_name,
            )
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                world = world_view(connection, world_id)
            return JSONResponse(
                {"world": world, "replayed": replayed},
                status_code=200 if replayed else 201,
            )
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds/{world_id}", methods=["GET"])
async def get_world(request: Request) -> JSONResponse:
    try:
        return JSONResponse(_with_database(world_view, request.path_params["world_id"]))
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds/{world_id}/snapshot", methods=["GET"])
async def get_snapshot(request: Request) -> JSONResponse:
    try:
        return JSONResponse(_with_database(snapshot_view, request.path_params["world_id"]))
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds/{world_id}/data/{section}", methods=["GET"])
async def get_data(request: Request) -> JSONResponse:
    try:
        section = request.path_params["section"]

        def view(connection: DbConnection, world_id: UUID) -> dict[str, Any]:
            return {
                "worldId": str(world_id),
                "section": section,
                "items": data_view(connection, world_id, section),
            }

        return JSONResponse(_with_database(view, request.path_params["world_id"]))
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds/{world_id}/recovery", methods=["GET"])
async def get_recovery(request: Request) -> JSONResponse:
    try:
        result = _with_database(recovery_batch_view, request.path_params["world_id"])
        return JSONResponse({"batch": result})
    except Exception as error:
        return _error_response(error)


def _authorized_runtime(request: Request) -> bool:
    expected = os.getenv("AIRSTRONG_RUNTIME_TOKEN", "").strip()
    supplied = request.headers.get("Authorization", "")
    return bool(expected) and secrets.compare_digest(supplied, f"Bearer {expected}")


@mcp.custom_route("/api/worlds/{world_id}/recovery/evaluate", methods=["POST"])
async def post_recovery_evaluate(request: Request) -> JSONResponse:
    if not _authorized_runtime(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        world_id = _world_id(request.path_params["world_id"])
        body = await request.json()
        source = str(body["source"])
        sandbox_result = body["sandboxResult"]
        with connect(_database_url()) as connection:
            snapshot = load_snapshot(connection, world_id)
            artifact_hash = persist_generated_artifact(
                connection,
                snapshot,
                source=source,
                sandbox_stdout=sandbox_result,
                trueforge_session_id=str(body["trueforgeSessionId"]),
                trueforge_turn_id=str(body["trueforgeTurnId"]),
                sandbox_id=str(body["sandboxId"]),
            )
            if sandbox_result.get("artifactHash") != artifact_hash:
                raise ValueError("Sandbox artifact hash does not match submitted source")
            candidates = validated_candidates(
                snapshot,
                list(sandbox_result["candidates"]),
                artifact_hash=artifact_hash,
            )
            evaluations, ranked = evaluate_generated_candidates(snapshot, candidates)
            batch_id = persist_recovery_batch(connection, snapshot, candidates, evaluations, ranked)
            return JSONResponse(
                {
                    "batchId": str(batch_id),
                    "batch": recovery_batch_view(connection, world_id),
                    "lineage": {
                        "artifactHash": artifact_hash,
                        "trueforgeSessionId": str(body["trueforgeSessionId"]),
                        "trueforgeTurnId": str(body["trueforgeTurnId"]),
                        "sandboxId": str(body["sandboxId"]),
                    },
                },
                status_code=201,
            )
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds/{world_id}/scenarios/hero", methods=["POST"])
async def post_hero_scenario(request: Request) -> JSONResponse:
    try:
        world_id = _world_id(request.path_params["world_id"])
        idempotency_key = request.headers.get("Idempotency-Key", "")
        with connect(_database_url()) as connection:
            result = trigger_hero_scenario(connection, world_id, idempotency_key=idempotency_key)
            return JSONResponse(public_value(asdict(result)), status_code=200 if result.replayed else 201)
    except Exception as error:
        return _error_response(error)


@mcp.custom_route("/api/worlds/{world_id}/reset", methods=["POST"])
async def post_reset(request: Request) -> JSONResponse:
    try:
        world_id = _world_id(request.path_params["world_id"])
        idempotency_key = request.headers.get("Idempotency-Key", "")
        with connect(_database_url()) as connection:
            revision = reset_world(connection, world_id, idempotency_key=idempotency_key)
            return JSONResponse({"worldId": str(world_id), "worldRevision": revision})
    except Exception as error:
        return _error_response(error)


def _sse_event(event: dict[str, Any]) -> str:
    data = json.dumps(public_value(event), sort_keys=True, separators=(",", ":"))
    return f"id: {event['sequence']}\nevent: {event['eventType']}\ndata: {data}\n\n"


async def _async_events_after(
    connection: psycopg.AsyncConnection[DbRow],
    world_id: UUID,
    sequence: int,
) -> list[dict[str, Any]]:
    cursor = await connection.execute(
        """
        SELECT sequence, event_type, world_revision, payload, created_at
        FROM airline_world_events
        WHERE world_id = %s AND sequence > %s
        ORDER BY sequence
        """,
        (world_id, sequence),
    )
    rows = await cursor.fetchall()
    return [
        {
            "sequence": row["sequence"],
            "eventType": row["event_type"],
            "worldRevision": row["world_revision"],
            "payload": row["payload"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


async def _event_stream(world_id: UUID, after: int, *, follow: bool) -> AsyncIterator[str]:
    connection = await psycopg.AsyncConnection.connect(
        _database_url(),
        autocommit=True,
        row_factory=dict_row,
    )
    async with connection:
        await connection.execute("LISTEN airline_world_events")
        cursor = after
        for event in await _async_events_after(connection, world_id, cursor):
            cursor = event["sequence"]
            yield _sse_event(event)
        if not follow:
            return
        while True:
            received = False
            async for notification in connection.notifies(timeout=15, stop_after=1):
                received = True
                try:
                    notice = json.loads(notification.payload)
                except json.JSONDecodeError:
                    continue
                if notice.get("worldId") != str(world_id):
                    continue
                for event in await _async_events_after(connection, world_id, cursor):
                    cursor = event["sequence"]
                    yield _sse_event(event)
            if not received:
                yield ": keepalive\n\n"


@mcp.custom_route("/api/worlds/{world_id}/events", methods=["GET"])
async def get_events(request: Request) -> Response:
    try:
        world_id = _world_id(request.path_params["world_id"])
        try:
            query_after = int(request.query_params.get("after", "0"))
            header_after = int(request.headers.get("Last-Event-ID", "0"))
        except ValueError:
            return JSONResponse(
                {"error": "invalid_request", "detail": "event cursor must be an integer"},
                status_code=400,
            )
        if query_after < 0 or header_after < 0:
            return JSONResponse(
                {"error": "invalid_request", "detail": "event cursor cannot be negative"},
                status_code=400,
            )
        after = max(query_after, header_after)
        follow = request.query_params.get("follow", "true").lower() != "false"
        with connect(_database_url()) as connection:
            load_world(connection, world_id)
            if not follow:
                replay = events_after(connection, world_id, after)
                return StreamingResponse(
                    iter(_sse_event(event) for event in replay),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
        return StreamingResponse(
            _event_stream(world_id, after, follow=True),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as error:
        return _error_response(error)


def main() -> None:
    initialize_database()
    mcp.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "4200")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
