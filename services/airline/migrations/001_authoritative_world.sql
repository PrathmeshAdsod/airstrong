CREATE TABLE IF NOT EXISTS airline_worlds (
    world_id uuid PRIMARY KEY,
    display_name text NOT NULL,
    baseline_version text NOT NULL,
    simulation_clock timestamptz NOT NULL,
    revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
    next_event_sequence bigint NOT NULL DEFAULT 1 CHECK (next_event_sequence > 0),
    state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'expired')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS airline_airports (
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    code text NOT NULL,
    name text NOT NULL,
    city text NOT NULL,
    country_code text NOT NULL CHECK (length(country_code) = 2),
    timezone text NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    hourly_capacity integer NOT NULL CHECK (hourly_capacity > 0),
    domestic_connection_minutes integer NOT NULL CHECK (domestic_connection_minutes > 0),
    international_connection_minutes integer NOT NULL CHECK (international_connection_minutes >= domestic_connection_minutes),
    PRIMARY KEY (world_id, code)
);

CREATE TABLE IF NOT EXISTS airline_aircraft (
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    aircraft_id text NOT NULL CHECK (aircraft_id ~ '^ALN-A[0-9]{2}$'),
    aircraft_type text NOT NULL,
    seats integer NOT NULL CHECK (seats > 0),
    location_airport text NOT NULL,
    status text NOT NULL CHECK (status IN ('available', 'unavailable')),
    available_from timestamptz NOT NULL,
    minimum_turnaround_minutes integer NOT NULL CHECK (minimum_turnaround_minutes > 0),
    PRIMARY KEY (world_id, aircraft_id),
    FOREIGN KEY (world_id, location_airport) REFERENCES airline_airports(world_id, code)
);

CREATE TABLE IF NOT EXISTS airline_flights (
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    flight_id text NOT NULL CHECK (flight_id ~ '^ALN-[0-9]{4}$'),
    origin text NOT NULL,
    destination text NOT NULL,
    scheduled_departure timestamptz NOT NULL,
    scheduled_arrival timestamptz NOT NULL,
    aircraft_id text NOT NULL,
    aircraft_type text NOT NULL,
    capacity integer NOT NULL CHECK (capacity > 0),
    status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'at_risk', 'cancelled', 'completed')),
    PRIMARY KEY (world_id, flight_id),
    FOREIGN KEY (world_id, origin) REFERENCES airline_airports(world_id, code),
    FOREIGN KEY (world_id, destination) REFERENCES airline_airports(world_id, code),
    FOREIGN KEY (world_id, aircraft_id) REFERENCES airline_aircraft(world_id, aircraft_id),
    CHECK (origin <> destination),
    CHECK (scheduled_arrival > scheduled_departure)
);

CREATE INDEX IF NOT EXISTS airline_flights_aircraft_rotation_idx
    ON airline_flights(world_id, aircraft_id, scheduled_departure);
CREATE INDEX IF NOT EXISTS airline_flights_airport_departure_idx
    ON airline_flights(world_id, origin, scheduled_departure);
CREATE INDEX IF NOT EXISTS airline_flights_airport_arrival_idx
    ON airline_flights(world_id, destination, scheduled_arrival);

CREATE TABLE IF NOT EXISTS airline_crew (
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    crew_id text NOT NULL CHECK (crew_id ~ '^ALN-R[0-9]{2}[CFAB]$'),
    role text NOT NULL CHECK (role IN ('captain', 'first_officer', 'cabin')),
    base_airport text NOT NULL,
    qualifications text[] NOT NULL CHECK (cardinality(qualifications) > 0),
    duty_start timestamptz NOT NULL,
    duty_end timestamptz NOT NULL,
    previous_duty_end timestamptz NOT NULL,
    PRIMARY KEY (world_id, crew_id),
    FOREIGN KEY (world_id, base_airport) REFERENCES airline_airports(world_id, code),
    CHECK (duty_end > duty_start),
    CHECK (duty_start > previous_duty_end)
);

CREATE TABLE IF NOT EXISTS airline_crew_assignments (
    world_id uuid NOT NULL,
    crew_id text NOT NULL,
    flight_id text NOT NULL,
    role text NOT NULL CHECK (role IN ('captain', 'first_officer', 'cabin')),
    PRIMARY KEY (world_id, crew_id, flight_id),
    FOREIGN KEY (world_id, crew_id) REFERENCES airline_crew(world_id, crew_id) ON DELETE CASCADE,
    FOREIGN KEY (world_id, flight_id) REFERENCES airline_flights(world_id, flight_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS airline_crew_assignments_flight_idx
    ON airline_crew_assignments(world_id, flight_id);

CREATE TABLE IF NOT EXISTS airline_passenger_parties (
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    party_id text NOT NULL CHECK (party_id ~ '^ALN-PAX-[0-9]{4}$'),
    party_size integer NOT NULL CHECK (party_size BETWEEN 1 AND 9),
    PRIMARY KEY (world_id, party_id)
);

CREATE TABLE IF NOT EXISTS airline_itinerary_legs (
    world_id uuid NOT NULL,
    party_id text NOT NULL,
    flight_id text NOT NULL,
    leg_order integer NOT NULL CHECK (leg_order > 0),
    PRIMARY KEY (world_id, party_id, leg_order),
    UNIQUE (world_id, party_id, flight_id),
    FOREIGN KEY (world_id, party_id) REFERENCES airline_passenger_parties(world_id, party_id) ON DELETE CASCADE,
    FOREIGN KEY (world_id, flight_id) REFERENCES airline_flights(world_id, flight_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS airline_itinerary_legs_flight_idx
    ON airline_itinerary_legs(world_id, flight_id);

CREATE TABLE IF NOT EXISTS airline_scenario_invocations (
    invocation_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    scenario_key text NOT NULL,
    idempotency_key text NOT NULL,
    applied_revision integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (world_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS airline_disruptions (
    disruption_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    invocation_id uuid REFERENCES airline_scenario_invocations(invocation_id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('airport_capacity', 'aircraft_unavailable', 'runway_closure', 'crew_duty')),
    airport_code text,
    aircraft_id text,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    capacity_multiplier double precision CHECK (capacity_multiplier BETWEEN 0 AND 1),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (world_id, airport_code) REFERENCES airline_airports(world_id, code),
    FOREIGN KEY (world_id, aircraft_id) REFERENCES airline_aircraft(world_id, aircraft_id),
    CHECK (ends_at > starts_at),
    CHECK (airport_code IS NOT NULL OR aircraft_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS airline_disruptions_world_time_idx
    ON airline_disruptions(world_id, starts_at, ends_at);

CREATE TABLE IF NOT EXISTS airline_operational_impacts (
    impact_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    world_revision integer NOT NULL,
    entity_type text NOT NULL CHECK (entity_type IN ('flight', 'crew', 'passenger_party')),
    entity_id text NOT NULL,
    reason text NOT NULL,
    depth integer NOT NULL CHECK (depth >= 0),
    root_disruption_id uuid NOT NULL REFERENCES airline_disruptions(disruption_id) ON DELETE CASCADE,
    source_entity_type text,
    source_entity_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (world_id, world_revision, entity_type, entity_id, root_disruption_id, reason)
);

CREATE INDEX IF NOT EXISTS airline_operational_impacts_world_idx
    ON airline_operational_impacts(world_id, world_revision, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS airline_world_events (
    world_id uuid NOT NULL REFERENCES airline_worlds(world_id) ON DELETE CASCADE,
    sequence bigint NOT NULL CHECK (sequence > 0),
    event_type text NOT NULL,
    world_revision integer NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (world_id, sequence)
);

CREATE INDEX IF NOT EXISTS airline_world_events_created_idx
    ON airline_world_events(world_id, created_at);
