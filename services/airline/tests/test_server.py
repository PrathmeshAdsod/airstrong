from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import anyio
import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from airstrong_airline.database import connect, migrate
from airstrong_airline.server import initialize_database, mcp

DATABASE_URL = os.getenv("AIRSTRONG_TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


@contextmanager
def running_server() -> Iterator[str]:
    if not DATABASE_URL:
        pytest.skip("AIRSTRONG_TEST_DATABASE_URL is not configured")
    os.environ["AIRSTRONG_DATABASE_URL"] = DATABASE_URL
    initialize_database()
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        host="127.0.0.1",
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            lifespan="on",
        )
    )

    def run_server() -> None:
        if os.name == "nt":
            asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
        else:
            asyncio.run(server.serve())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("Airline test server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    with running_server() as url:
        yield url


@pytest.fixture()
def api_world(server_url: str) -> Iterator[tuple[str, UUID]]:
    key = f"api-world-{uuid4()}"
    with httpx.Client(base_url=server_url, timeout=10) as client:
        response = client.post(
            "/api/worlds",
            headers={"Idempotency-Key": key},
            json={"displayName": "Aliens Airline"},
        )
        assert response.status_code == 201
        world_id = UUID(response.json()["world"]["worldId"])
        replay = client.post(
            "/api/worlds",
            headers={"Idempotency-Key": key},
            json={"displayName": "Ignored on replay"},
        )
        assert replay.status_code == 200
        assert replay.json()["world"]["worldId"] == str(world_id)
    try:
        yield server_url, world_id
    finally:
        with connect(DATABASE_URL) as connection:
            migrate(connection)
            with connection.transaction():
                connection.execute("DELETE FROM airline_worlds WHERE world_id = %s", (world_id,))


def _event_ids(body: str) -> list[int]:
    return [int(line.removeprefix("id: ")) for line in body.splitlines() if line.startswith("id: ")]


def test_rest_data_and_scenario_mutation_are_authoritative(api_world: tuple[str, UUID]) -> None:
    server_url, world_id = api_world
    with httpx.Client(base_url=server_url, timeout=10) as client:
        flights_before = client.get(f"/api/worlds/{world_id}/data/flights").json()["items"]
        assert flights_before
        assert {item["status"] for item in flights_before} == {"scheduled"}

        first = client.post(
            f"/api/worlds/{world_id}/scenarios/hero",
            headers={"Idempotency-Key": "hero-api-once"},
        )
        replay = client.post(
            f"/api/worlds/{world_id}/scenarios/hero",
            headers={"Idempotency-Key": "hero-api-once"},
        )
        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["scenarioInvocationId"] == first.json()["scenarioInvocationId"]

        snapshot = client.get(f"/api/worlds/{world_id}/snapshot").json()
        assert snapshot["revision"] == 1
        assert len(snapshot["disruptions"]) == 2
        assert snapshot["operationalImpacts"]
        flights_after = client.get(f"/api/worlds/{world_id}/data/flights").json()["items"]
        assert any(item["status"] == "at_risk" for item in flights_after)


def test_sse_replays_exactly_after_a_durable_cursor(api_world: tuple[str, UUID]) -> None:
    server_url, world_id = api_world
    with httpx.Client(base_url=server_url, timeout=10) as client:
        client.post(
            f"/api/worlds/{world_id}/scenarios/hero",
            headers={"Idempotency-Key": "hero-sse-once"},
        ).raise_for_status()
        complete = client.get(f"/api/worlds/{world_id}/events?follow=false")
        assert complete.status_code == 200
        assert _event_ids(complete.text) == [1, 2, 3]

        resumed = client.get(
            f"/api/worlds/{world_id}/events?follow=false",
            headers={"Last-Event-ID": "2"},
        )
        assert _event_ids(resumed.text) == [3]
        assert "scenario.triggered" not in resumed.text
        assert "world.recalculated" in resumed.text


def test_sse_pushes_postgres_notifications_without_frontend_polling(api_world: tuple[str, UUID]) -> None:
    server_url, world_id = api_world
    received_ids: list[int] = []
    with (
        httpx.Client(base_url=server_url, timeout=10) as stream_client,
        httpx.Client(base_url=server_url, timeout=10) as mutation_client,
        stream_client.stream("GET", f"/api/worlds/{world_id}/events?after=1") as response,
    ):
        response.raise_for_status()
        mutation_client.post(
            f"/api/worlds/{world_id}/scenarios/hero",
            headers={"Idempotency-Key": "hero-live-event"},
        ).raise_for_status()
        for line in response.iter_lines():
            if line.startswith("id: "):
                received_ids.append(int(line.removeprefix("id: ")))
            if received_ids == [2, 3]:
                break
    assert received_ids == [2, 3]


async def _remote_mcp_probe(server_url: str, world_id: UUID) -> tuple[list[str], dict]:
    async with (
        streamable_http_client(f"{server_url}/mcp", terminate_on_close=False) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool(
            "airline_aircraft_investigation",
            {"world_id": str(world_id)},
        )
        assert result.is_error is False
        payload = result.structured_content
        if payload is None:
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
        return sorted(tool.name for tool in tools.tools), payload


def test_remote_mcp_discovers_and_calls_real_airline_tools(api_world: tuple[str, UUID]) -> None:
    server_url, world_id = api_world
    with httpx.Client(base_url=server_url, timeout=10) as client:
        client.post(
            f"/api/worlds/{world_id}/scenarios/hero",
            headers={"Idempotency-Key": "hero-mcp-once"},
        ).raise_for_status()

    tool_names, payload = anyio.run(_remote_mcp_probe, server_url, world_id)

    assert tool_names == [
        "airline_aircraft_investigation",
        "airline_crew_investigation",
        "airline_passenger_investigation",
        "airline_recovery_candidates",
        "airline_world_snapshot",
    ]
    assert payload["worldRevision"] == 1
    assert payload["unavailableAircraft"]
