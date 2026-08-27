from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

AircraftStatus = Literal["available", "unavailable"]
FlightStatus = Literal["scheduled", "at_risk", "cancelled", "completed"]
CrewRole = Literal["captain", "first_officer", "cabin"]
ImpactEntity = Literal["flight", "crew", "passenger_party"]


@dataclass(frozen=True, slots=True)
class Airport:
    code: str
    name: str
    city: str
    country_code: str
    timezone: str
    latitude: float
    longitude: float
    hourly_capacity: int
    domestic_connection_minutes: int
    international_connection_minutes: int


@dataclass(frozen=True, slots=True)
class Aircraft:
    aircraft_id: str
    aircraft_type: str
    seats: int
    location_airport: str
    status: AircraftStatus
    available_from: datetime
    minimum_turnaround_minutes: int


@dataclass(frozen=True, slots=True)
class Flight:
    flight_id: str
    origin: str
    destination: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    aircraft_id: str
    aircraft_type: str
    capacity: int
    status: FlightStatus = "scheduled"


@dataclass(frozen=True, slots=True)
class CrewMember:
    crew_id: str
    role: CrewRole
    base_airport: str
    qualifications: tuple[str, ...]
    duty_start: datetime
    duty_end: datetime
    previous_duty_end: datetime


@dataclass(frozen=True, slots=True)
class CrewAssignment:
    crew_id: str
    flight_id: str
    role: CrewRole


@dataclass(frozen=True, slots=True)
class PassengerParty:
    party_id: str
    party_size: int


@dataclass(frozen=True, slots=True)
class ItineraryLeg:
    party_id: str
    flight_id: str
    leg_order: int


@dataclass(frozen=True, slots=True)
class Disruption:
    disruption_id: UUID
    kind: str
    airport_code: str | None
    starts_at: datetime
    ends_at: datetime
    capacity_multiplier: float | None
    aircraft_id: str | None


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    world_id: UUID
    revision: int
    airports: tuple[Airport, ...]
    aircraft: tuple[Aircraft, ...]
    flights: tuple[Flight, ...]
    crew: tuple[CrewMember, ...]
    crew_assignments: tuple[CrewAssignment, ...]
    passenger_parties: tuple[PassengerParty, ...]
    itinerary_legs: tuple[ItineraryLeg, ...]
    disruptions: tuple[Disruption, ...]


@dataclass(frozen=True, slots=True)
class OperationalImpact:
    entity_type: ImpactEntity
    entity_id: str
    reason: str
    depth: int
    root_disruption_id: UUID
    source_entity_type: str | None = None
    source_entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    world_id: UUID
    world_revision: int
    scenario_key: str
    scenario_invocation_id: UUID
    disruption_ids: tuple[UUID, ...]
    impacts: tuple[OperationalImpact, ...]
    replayed: bool
