# Synthetic airline domain assumptions

Airstrong uses a fictional airline and a deliberately small, versioned operating day. The rules below are product assumptions for a defensible simulation, not a claim that they reproduce any carrier's operations manual or the complete regulations of a jurisdiction.

## Public operational grounding

- Crew duty and rest are explicit constraints. EASA ORO.FTL establishes cumulative duty limits and requires minimum rest before a flight duty period. Airstrong PR2 uses a conservative simplified gate of at most 13 hours for one seeded duty and at least 10 hours since the previous duty. Later candidate validation must still use the stored duty window for every reassignment. Source: [EASA Easy Access Rules for Air Operations, ORO.FTL.210 and ORO.FTL.235](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-air-operations).
- Turnaround is modeled per aircraft type and checked between every consecutive leg. ICAO describes turnaround as a coordinated operator-specific plan rather than one universal duration. The seed therefore stores transparent synthetic minima of 50 minutes for A320neo and 55 minutes for A321neo. Source: [ICAO aircraft turnround model guidance](https://www.icao.int/sites/default/files/MID/Documents/MIDANPIRG%2019%20%26%20RASG-MID%209/Working%20Papers/WP26-AGA-AOP-Safety-Matters.pdf).
- Connection time is airport and journey specific. FAA material notes that minimum connection times vary by airline, airport, time, and sometimes flight. The seed stores visible synthetic minima of 45 minutes for domestic connections and 75 minutes when either adjacent leg is international. Source: [FAA Terminal Area Plan environmental assessment](https://www.faa.gov/sites/faa.gov/files/TAP_Final_EA_Chapter_2.pdf).
- Airport restrictions are represented as capacity changes over time. ICAO contingency guidance calls for operational or capacity restrictions to be coordinated during aerodrome disruption and recovery. Airstrong applies capacity to chronological hourly movements, then discovers overflow from the current database state. Source: [ICAO contingency aerodromes guidance](https://www.icao.int/operational-safety/contingency-aerodromes).

## PR2 hard rules

- An aircraft begins at a stored airport, follows a location-continuous rotation, matches the assigned aircraft type, and observes its configured minimum turnaround.
- Every flight has one captain, one first officer, and at least two cabin crew in the seed. Crew role, qualification, duty window, assignment overlap, duty duration, and preceding rest are validated.
- Passenger parties have contiguous itineraries, airport-continuous legs, enough connection time, and cannot exceed flight capacity.
- The hero scenario performs two real mutations: a temporary BOM capacity reduction and unavailability of the aircraft recorded as `ALN-A03`. These are injected scenario facts, not candidate outcomes.
- Capacity overflow, downstream aircraft rotations, affected crew, and affected passenger itineraries are recalculated from the authoritative snapshot after mutation.
- Counts, dependency depth, and at-risk flight state are stored from the calculation. No future recovery candidate, violation, winner, or plan label exists in the baseline.

These assumptions are intentionally inspectable and replaceable. Changing airport capacity, a rotation, a crew window, or an itinerary in PostgreSQL changes the calculated impact.
