from __future__ import annotations

import os
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from .store import audit_state, commit_once, ensure_schema


class CompatibilitySnapshot(BaseModel):
    service: str
    probe_values: list[int]
    total_writes: int


class CompatibilityAudit(BaseModel):
    idempotency_key: str
    exists: bool
    total_writes: int


class CompatibilityCommit(BaseModel):
    idempotency_key: str
    inserted: bool
    total_writes: int


mcp = MCPServer(
    "Airstrong sponsor compatibility",
    instructions=(
        "This server exists only to prove real MCP discovery, PostgreSQL reads, "
        "approval-gated idempotent writes, and TrueForge Code Mode integration."
    ),
)


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def compatibility_snapshot() -> CompatibilitySnapshot:
    """Read a small real PostgreSQL-backed snapshot for Code Mode processing."""
    state = audit_state("__snapshot__")
    return CompatibilitySnapshot(
        service="airstrong-compatibility-mcp",
        probe_values=[3, 5, 8, 13],
        total_writes=state.total_writes,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def compatibility_audit(
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
) -> CompatibilityAudit:
    """Read whether a compatibility write exists without changing state."""
    state = audit_state(idempotency_key)
    return CompatibilityAudit(
        idempotency_key=idempotency_key,
        exists=state.exists,
        total_writes=state.total_writes,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def compatibility_commit(
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
    payload: Annotated[str, Field(min_length=1, max_length=512)],
) -> CompatibilityCommit:
    """Perform one real idempotent PostgreSQL write after runtime approval."""
    inserted, state = commit_once(idempotency_key, payload)
    return CompatibilityCommit(
        idempotency_key=idempotency_key,
        inserted=inserted,
        total_writes=state.total_writes,
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    try:
        ensure_schema()
    except Exception as error:  # pragma: no cover - exercised by container health checks
        return JSONResponse({"status": "error", "detail": str(error)}, status_code=503)
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("AIRSTRONG_MCP_PORT", "4100")),
        stateless_http=True,
        json_response=True,
    )
