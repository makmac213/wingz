# Business Requirements Document

---

## Document Header

| Field | Value |
|---|---|
| **Document Title** | Wingz Ride Management API — Django REST Framework |
| **Document ID** | BRD-2026-001 |
| **Date** | 2026-06-26 |
| **Version** | 1.0 |
| **Prepared By** | Business Analyst |
| **Status** | Draft |

---

## Executive Summary

Wingz requires a RESTful API built on Django REST Framework to manage ride lifecycle data including rides, users (riders and drivers), and ride events. The system must expose full CRUD operations on all three domain entities, enforce admin-only access at every endpoint, and deliver a high-performance ride listing endpoint capable of filtering, multi-mode sorting, and pagination against arbitrarily large datasets without degrading database performance. The expected outcome is a production-quality Django API that can serve as the data backbone for ride dispatch and operational reporting workflows.

---

## Business Objectives

- Provide a complete, authenticated CRUD API over the Ride, User, and RideEvent data entities so that operations staff can manage ride records programmatically.
- Enforce strict role-based access control so that only users with the `admin` role can interact with any API endpoint, eliminating unauthorized data exposure.
- Deliver a paginated Ride list endpoint that supports simultaneous filtering by ride status and rider email, and sorting by either pickup time or proximity to a GPS coordinate, within a single unified endpoint.
- Ensure the Ride list endpoint executes no more than 2 database queries (or 3 when counting the pagination COUNT query) regardless of dataset size, preventing N+1 query degradation on large ride tables.
- Guarantee that the `todays_ride_events` field in the Ride list response never loads the full RideEvent history for any ride — only events from the last 24 hours must be fetched at the SQL level.
- Provide a documented raw SQL analytical query that surfaces rides whose pickup-to-dropoff duration exceeds one hour, grouped by month and driver, to support operational reporting.

---

## Problem Statement

Ride dispatch operations require a centralized, machine-readable API to create, read, update, and delete ride records and their associated events. Without such an API, operational tooling must interact with the database directly, which is unsafe and unscalable. Additionally, ride listing views in operational dashboards must surface recent activity (today's ride events) per ride without triggering full table scans or N+1 query patterns — a common failure mode in ORM-based systems. The absence of a well-designed, performance-constrained list endpoint would make real-time operational views unusable at scale. Finally, management requires analytical SQL to identify long-duration trips for cost and efficiency reporting, which must be available in documented form.

---

## Scope

### In Scope

- Django project setup with Django REST Framework installed and configured.
- Three data models: `User`, `Ride`, and `RideEvent`, with the exact field definitions specified in the assessment.
- DRF serializers for all three models covering full CRUD operations.
- DRF ViewSets for all three models exposing standard CRUD endpoints (list, create, retrieve, update, partial update, destroy).
- Admin-only authentication and authorization enforced globally across all endpoints.
- A Ride list endpoint (`GET /rides/` or equivalent) supporting:
  - Pagination (page-based or cursor-based).
  - Filter by `status` field.
  - Filter by rider email address.
  - Sort by `pickup_time`.
  - Sort by distance to a caller-supplied GPS coordinate (latitude and longitude as query parameters).
  - Inline `todays_ride_events` field scoped to the last 24 hours, fetched without loading full RideEvent history.
  - Embedded rider and driver user objects.
  - Maximum 2 database queries for data (plus 1 optional COUNT query for pagination).
- A documented raw SQL query (included in project README) for long-duration trip reporting grouped by month and driver.
- Error handling for invalid query parameters, missing authentication, and authorization failures.

### Out of Scope

- End-user (non-admin) authentication flows, registration, or password management.
- Real-time WebSocket or push-notification features.
- Frontend or mobile client applications.
- Payment processing or fare calculation logic.
- GPS tracking, geofencing, or live location streaming.
- Driver assignment or dispatching logic.
- Third-party mapping or routing service integrations.
- Automated test suite implementation (testing strategy is an evaluation criterion but no test framework setup is mandated by the assessment spec).
- Deployment infrastructure, Docker configuration, or CI/CD pipelines.
- Data migration scripts from legacy systems.
- Soft-delete or archival patterns beyond what is implied by the `status` field.

### Assumptions

- The `User` model is the system's user entity (it may or may not extend Django's built-in `AbstractUser`; the engineer decides based on the field set specified).
- `id_rider` and `id_driver` on the `Ride` model are both foreign keys to the same `User` model. Riders have `role='rider'` and drivers have `role='driver'`; a single user cannot serve as both on the same ride.
- "Last 24 hours" for `todays_ride_events` is computed relative to the server's current UTC timestamp at request time.
- Distance-based sorting uses a Euclidean approximation or equivalent in-database computation against the pickup coordinates (`pickup_latitude`, `pickup_longitude`); haversine accuracy is not mandated unless the engineer deems it necessary.
- Admin role is determined solely by the `role` field on the `User` model (value: `'admin'`); Django's built-in `is_staff` or `is_superuser` flags are not required to align with this role.
- The pagination COUNT query is treated as a third query and does not violate the "max 2 queries for data" constraint.
- The assessment does not require multi-tenancy; all admin users have access to all records.

### Constraints

- The solution must use Django REST Framework.
- Database query count for the Ride list endpoint must not exceed 2 data queries (3 including COUNT).
- The `todays_ride_events` field must be resolved at the SQL layer — no Python-level filtering of a fully-loaded queryset is acceptable.
- The sort-by-distance and sort-by-pickup-time modes must co-exist within a single endpoint (not separate endpoints).
- Pagination must remain functional and correct regardless of which sort mode is active.
- The raw SQL analytical query must be valid SQL compatible with a standard relational database (PostgreSQL preferred given DRF ecosystem conventions).

---

## Stakeholders

| Stakeholder | Role | Interest / Impact |
|---|---|---|
| Wingz Engineering Assessor | Evaluator | Reviews code quality, correctness, performance, and error handling against assessment criteria |
| Operations Staff (implicit end user) | Admin API Consumer | Needs reliable CRUD access to ride and user data |
| Reporting / Management (implicit) | Data Consumer | Needs the long-duration trip SQL for operational insights |
| Senior Fullstack Engineer (implementer) | Technical Implementer | Receives this BRD as the primary implementation specification |

---

## Functional Requirements

### Authentication & Authorization

- **FR-001**: The system shall reject any request to any endpoint with an HTTP 401 response when the request does not include valid authentication credentials.
- **FR-002**: The system shall reject any request with an HTTP 403 response when the authenticated user's `role` field value is not `'admin'`.
- **FR-003**: The system shall permit full CRUD operations on all endpoints when the authenticated user has `role = 'admin'`.

### User Model & Endpoints

- **FR-004**: The system shall persist `User` records with the following fields: `id_user` (primary key), `role` (VARCHAR, values restricted to `'admin'`, `'rider'`, and `'driver'`), `first_name`, `last_name`, `email`, `phone_number`.
- **FR-005**: The system shall expose a `User` list endpoint that returns all users in paginated form.
- **FR-006**: The system shall expose a `User` detail endpoint that returns a single user by primary key.
- **FR-007**: The system shall expose a `User` create endpoint that persists a new user record and returns the created object with HTTP 201.
- **FR-008**: The system shall expose a `User` update endpoint (full and partial) that modifies an existing user record and returns the updated object.
- **FR-009**: The system shall expose a `User` delete endpoint that removes a user record and returns HTTP 204.

### Ride Model & Endpoints

- **FR-010**: The system shall persist `Ride` records with the following fields: `id_ride` (primary key), `status` (VARCHAR, values restricted to `'en-route'`, `'pickup'`, `'dropoff'`), `id_rider` (FK to User), `id_driver` (FK to User), `pickup_latitude` (FLOAT), `pickup_longitude` (FLOAT), `dropoff_latitude` (FLOAT), `dropoff_longitude` (FLOAT), `pickup_time` (DATETIME).
- **FR-011**: The system shall expose a `Ride` create endpoint that persists a new ride record and returns the created object with HTTP 201.
- **FR-012**: The system shall expose a `Ride` detail endpoint that returns a single ride by primary key, including embedded rider, driver, and all associated RideEvents.
- **FR-013**: The system shall expose a `Ride` update endpoint (full and partial) that modifies an existing ride record and returns the updated object.
- **FR-014**: The system shall expose a `Ride` delete endpoint that removes a ride record and returns HTTP 204.

### Ride List Endpoint

- **FR-015**: The system shall expose a `Ride` list endpoint that returns a paginated collection of ride records.
- **FR-016**: The Ride list endpoint shall include the following nested data for each ride: the full rider user object (referenced by `id_rider`), the full driver user object (referenced by `id_driver`), and all associated RideEvents for that ride.
- **FR-017**: The Ride list endpoint shall include a `todays_ride_events` field per ride containing only RideEvents whose `created_at` timestamp falls within the last 24 hours (relative to server UTC time at request time).
- **FR-018**: The system shall generate SQL for the `todays_ride_events` field that filters RideEvents at the database level — the ORM query must include a `WHERE created_at >= <24-hours-ago>` predicate and must not retrieve the full RideEvent table and filter in application memory.
- **FR-019**: The Ride list endpoint shall support filtering by ride `status` via a query parameter (e.g., `?status=en-route`). When this parameter is provided, only rides matching that status value shall be returned.
- **FR-020**: The Ride list endpoint shall support filtering by rider email address via a query parameter (e.g., `?rider_email=jane@example.com`). When this parameter is provided, only rides whose associated rider has a matching email shall be returned.
- **FR-021**: The Ride list endpoint shall support sorting by `pickup_time` in ascending order when a sort query parameter indicates pickup time ordering.
- **FR-022**: The Ride list endpoint shall support sorting by distance between the ride's `pickup_latitude`/`pickup_longitude` and a caller-supplied GPS coordinate, provided via query parameters (e.g., `?lat=37.7749&lon=-122.4194`), in ascending order (nearest first) when those parameters are present.
- **FR-023**: The sort-by-distance mode and sort-by-pickup-time mode shall exist within the same single endpoint — they must not be split into separate routes.
- **FR-024**: Pagination shall function correctly and return accurate page counts regardless of which sort mode (pickup time or distance) is active.
- **FR-025**: The Ride list endpoint shall execute no more than 2 database queries to fetch ride data and all associated nested objects (rider, driver, RideEvents, todays_ride_events). A third query for the pagination COUNT is permitted and does not constitute a violation of this constraint.
- **FR-026**: The system shall return an HTTP 400 response with a descriptive error message when the `lat` or `lon` query parameters are present but contain non-numeric or out-of-range values.
- **FR-027**: The system shall return an HTTP 400 response with a descriptive error message when an unrecognized `status` filter value is supplied.

### RideEvent Model & Endpoints

- **FR-028**: The system shall persist `RideEvent` records with the following fields: `id_ride_event` (primary key), `id_ride` (FK to Ride), `description` (VARCHAR), `created_at` (DATETIME).
- **FR-029**: The system shall expose a `RideEvent` create endpoint that persists a new event record linked to an existing ride and returns the created object with HTTP 201.
- **FR-030**: The system shall expose a `RideEvent` list endpoint that returns all events, optionally filterable by ride.
- **FR-031**: The system shall expose a `RideEvent` detail endpoint that returns a single event by primary key.
- **FR-032**: The system shall expose a `RideEvent` update endpoint (full and partial) that modifies an existing event record and returns the updated object.
- **FR-033**: The system shall expose a `RideEvent` delete endpoint that removes an event record and returns HTTP 204.

### Analytical SQL (Bonus)

- **FR-034**: The project README shall include a raw SQL query that returns all rides whose duration from `pickup_time` to dropoff exceeds 1 hour, grouped by calendar month and by driver, with the driver identified by their user record.
- **FR-035**: The raw SQL query referenced in FR-034 shall be valid, executable SQL against a standard relational database without requiring ORM execution context.

---

## Non-Functional Requirements

### Performance

- **NFR-001**: The Ride list endpoint must generate no more than 2 SQL data queries (plus 1 optional COUNT) regardless of dataset size or active filter/sort combination.
- **NFR-002**: The `todays_ride_events` filter must be applied at the SQL layer using a date predicate, never through Python-level iteration over fully-loaded querysets.
- **NFR-003**: Sort-by-distance computation shall be performed in the database (via annotated expression) rather than in application memory, so that database-level `ORDER BY` and `LIMIT`/`OFFSET` pagination remain efficient.
- **NFR-004**: All foreign key lookups for rider and driver on the Ride list must be resolved via a single join or prefetch, not via per-row lazy loading.
- **NFR-005**: The system must remain responsive under high ride table cardinality (tens of millions of rows). Indexes on `Ride.status`, `Ride.pickup_time`, `Ride.id_rider`, `RideEvent.created_at`, and `RideEvent.id_ride` are expected to be present or documented as required.

### Security

- **NFR-006**: All API endpoints must require authentication. Unauthenticated requests must return HTTP 401.
- **NFR-007**: All API endpoints must enforce admin-role authorization. Non-admin authenticated requests must return HTTP 403.
- **NFR-008**: No sensitive user data (e.g., phone numbers, emails) shall be exposed in error response bodies or server logs.

### Reliability & Error Handling

- **NFR-009**: The API must return structured JSON error responses (not HTML error pages) for all 4xx and 5xx error conditions.
- **NFR-010**: Invalid or missing required fields on create/update endpoints must return HTTP 400 with field-level validation error detail.
- **NFR-011**: Requests referencing non-existent primary keys (e.g., ride detail for an unknown `id_ride`) must return HTTP 404.

### Code Quality

- **NFR-012**: Serializer logic and view logic must be cleanly separated — business logic must not be embedded in views.
- **NFR-013**: The codebase must be free of N+1 query patterns detectable via Django's `django.db.connection.queries` debug output.

### Usability / Developer Experience

- **NFR-014**: All endpoints must return responses in JSON format with `Content-Type: application/json`.
- **NFR-015**: Query parameter names for filters and sorts must be documented (in code, docstrings, or README) so that API consumers can discover them without reading source code.

---

## Business Rules

- **BR-001**: A `Ride.status` field must only ever contain one of three values: `'en-route'`, `'pickup'`, or `'dropoff'`. Any other value must be rejected at the API layer before persistence.
- **BR-002**: A `User.role` field must only contain one of three values: `'admin'`, `'rider'`, or `'driver'`. The system must enforce this as a choice constraint at the API layer.
- **BR-003**: Both `id_rider` and `id_driver` on a Ride must reference records in the `User` table. A Ride cannot be created or updated to reference a non-existent User.
- **BR-004**: A `RideEvent` must always be linked to an existing `Ride`. A RideEvent cannot be created without a valid `id_ride` reference.
- **BR-005**: The "last 24 hours" window for `todays_ride_events` is always calculated as `NOW() - 24 hours` in UTC at query execution time. It is not calendar-day scoped (i.e., it is not "since midnight today").
- **BR-006**: Distance sorting is computed from the ride's pickup coordinates to the caller-supplied coordinate. Dropoff coordinates are not used in distance sorting.
- **BR-007**: When both `lat`/`lon` parameters and a pickup-time sort parameter are simultaneously supplied, the system must define a deterministic resolution (e.g., distance sort takes precedence, or an error is returned). This rule requires clarification — see Open Questions.
- **BR-008**: A `User` record referenced as a rider or driver on any existing `Ride` must not be deletable without first handling the referential integrity constraint. The system must not silently cascade-delete ride records when a user is deleted; the behavior must be explicitly defined.

---

## User Stories / Use Cases

### Admin User — Ride Management

> *As an admin user, I want to create a new ride record with rider, driver, and coordinate information so that the ride can be tracked from dispatch through completion.*

**Acceptance Criteria:**
- Given valid authentication as an admin, when I POST to the rides endpoint with all required fields, then I receive HTTP 201 and the created ride object including its `id_ride`.
- Given a `status` value of `'invalid'`, when I POST, then I receive HTTP 400 with a validation error on the `status` field.
- Given a `id_rider` that does not exist, when I POST, then I receive HTTP 400 with a relational validation error.

---

> *As an admin user, I want to retrieve a paginated list of rides filtered by status and sorted by pickup time so that I can review scheduled rides in chronological order.*

**Acceptance Criteria:**
- Given a GET request with `?status=en-route`, only rides with `status = 'en-route'` are returned.
- Given a GET request with no sort parameter, rides are returned in a consistent default order (pickup time ascending is acceptable as a default).
- Given a page size of N, the response includes no more than N ride objects and a pagination cursor or page number for the next page.
- Each ride in the response includes the rider user object, driver user object, all associated RideEvents, and the `todays_ride_events` list.

---

> *As an admin user, I want to retrieve rides sorted by proximity to my current GPS location so that I can identify the nearest active rides.*

**Acceptance Criteria:**
- Given a GET request with `?lat=37.7749&lon=-122.4194`, rides are returned sorted by ascending distance from that coordinate to each ride's pickup location.
- Given non-numeric values for `lat` or `lon`, I receive HTTP 400 with a descriptive error.
- Given only `lat` without `lon` (or vice versa), I receive HTTP 400 indicating both parameters are required for distance sort.
- Pagination applied to distance-sorted results returns the correct ordered subset on each page.

---

> *As an admin user, I want to filter rides by a specific rider's email address so that I can view the ride history for a particular customer.*

**Acceptance Criteria:**
- Given `?rider_email=jane@example.com`, only rides whose rider has email `jane@example.com` are returned.
- Given an email that matches no rider, an empty paginated list is returned (HTTP 200, empty results array).
- Given an invalid email format, the system returns HTTP 400.

---

### Admin User — Ride Event Tracking

> *As an admin user, I want to view only the ride events created in the last 24 hours for each ride in the list so that I can quickly assess recent activity without being overwhelmed by historical events.*

**Acceptance Criteria:**
- The `todays_ride_events` field in the Ride list response contains only events with `created_at >= now() - 24 hours`.
- An empty array is returned for rides with no events in the last 24 hours.
- Verifying via database query log that no query fetches all RideEvents without a `created_at` date filter.
- The full list of RideEvents (all time) for a ride is separately available via the Ride detail endpoint.

---

## Data Requirements

### Key Entities

| Entity | Description |
|---|---|
| `User` | Represents both riders and drivers. Identified by `id_user`. Role distinguishes admin from operational users. |
| `Ride` | Core transactional entity. Captures pickup/dropoff coordinates, timestamps, status, and references to rider and driver User records. |
| `RideEvent` | Append-style audit/event log linked to a specific Ride. Each event captures a description and creation timestamp. |

### Field Definitions

**User**
| Field | Type | Constraints |
|---|---|---|
| `id_user` | Integer / UUID | Primary Key, auto-generated |
| `role` | VARCHAR | Choices: `'admin'`, `'rider'`, `'driver'` |
| `first_name` | VARCHAR | Required |
| `last_name` | VARCHAR | Required |
| `email` | VARCHAR | Required, unique |
| `phone_number` | VARCHAR | Required |

**Ride**
| Field | Type | Constraints |
|---|---|---|
| `id_ride` | Integer / UUID | Primary Key, auto-generated |
| `status` | VARCHAR | Choices: `'en-route'`, `'pickup'`, `'dropoff'` |
| `id_rider` | FK → User | Required, no cascade delete |
| `id_driver` | FK → User | Required, no cascade delete |
| `pickup_latitude` | FLOAT | Required |
| `pickup_longitude` | FLOAT | Required |
| `dropoff_latitude` | FLOAT | Required |
| `dropoff_longitude` | FLOAT | Required |
| `pickup_time` | DATETIME | Required, timezone-aware recommended |

**RideEvent**
| Field | Type | Constraints |
|---|---|---|
| `id_ride_event` | Integer / UUID | Primary Key, auto-generated |
| `id_ride` | FK → Ride | Required, cascade delete acceptable |
| `description` | VARCHAR | Required |
| `created_at` | DATETIME | Auto-set on creation; must be indexed |

### Data Inputs and Outputs

- **Inputs**: JSON request bodies for create/update operations; query parameters for filtering and sorting.
- **Outputs**: JSON response bodies for all endpoints; paginated envelopes for list endpoints.

### Data Sensitivity

- `User.email` and `User.phone_number` are PII and must not appear in error response payloads beyond what is necessary for the requesting admin to perform their work.
- No financial data is stored. No HIPAA-regulated data is present.
- This system is an internal operational tool; data classification is "Internal / Operational PII."

### Data Migration

- No data migration is required. The system is greenfield.

---

## Integration Requirements

- No external system integrations are required for this assessment.
- The raw SQL query (FR-034, FR-035) may reference database-specific date functions (e.g., `DATE_TRUNC` for PostgreSQL, `STRFTIME` for SQLite). The implementation must document which database dialect is assumed.
- If Django's built-in authentication system is extended or replaced for admin-role enforcement, the mechanism must be documented so that future integrations (e.g., JWT, OAuth) can be layered on without structural rework.

---

## Success Metrics & KPIs

| Metric | Baseline | Target |
|---|---|---|
| Ride list endpoint database query count | Unconstrained (N+1 typical) | Max 2 data queries + 1 COUNT |
| `todays_ride_events` loaded via full-table scan | Likely (default ORM behavior) | Zero — SQL predicate required |
| Admin auth enforcement | Not implemented | 100% of endpoints reject non-admin |
| HTTP 400 returned for invalid filter params | Not implemented | 100% of invalid inputs produce structured 400 |
| Pagination consistency under sort change | Untested | Stable, correct page results in both sort modes |
| Raw SQL analytical query present in README | Absent | Present and executable |

---

## Dependencies & Risks

| Type | Description | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Technical | Distance sorting via annotated queryset may conflict with certain DRF pagination backends that re-order or re-query results | Medium | High | Engineer must validate that pagination `ORDER BY` is preserved when annotation is applied; use `RawQuerySet` or database-level expression as fallback |
| Technical | Django's `Prefetch` with a queryset-level filter (for `todays_ride_events`) must be validated to not produce a full-table scan | Medium | High | Verify index on `RideEvent.created_at`; confirm via `EXPLAIN` output that the filter is pushed to SQL |
| Technical | Using the same `User` model for both riders and drivers creates a self-referential FK pattern; Django requires `related_name` disambiguation | Low | Medium | Engineer must set `related_name='rides_as_rider'` and `related_name='rides_as_driver'` or equivalent |
| Design | The User model specification does not match Django's built-in `User` model field names (`id_user` vs `id`, `role` vs `is_staff`). Extending `AbstractUser` vs creating a fully custom model is an architectural decision with auth implications | Medium | Medium | Engineer to decide and document; if `AbstractUser` is extended, ensure `role` field is added cleanly |
| Scope | The assessment spec does not define a `dropoff_time` field on Ride, but the bonus SQL query requires trip duration (pickup to dropoff). This is a schema gap | High | High | See Open Questions — this must be resolved before implementation |
| Compliance | No regulatory constraints apply to this internal assessment project | N/A | N/A | N/A |

---

## Open Questions

1. **Dropoff time field**: The bonus SQL query (FR-034) requires computing pickup-to-dropoff duration greater than 1 hour. However, the `Ride` model specification does not include a `dropoff_time` field. Does the system need to add a `dropoff_time` field to the `Ride` model, or is this duration to be derived from RideEvent timestamps (e.g., the timestamp of the last event with status-related description)? This must be resolved before schema design begins.

2. ~~**Non-admin role value**~~ **RESOLVED**: The `User.role` field uses three distinct values: `'admin'`, `'rider'`, and `'driver'`. Riders and drivers are separate roles. A user cannot simultaneously be a rider and a driver.

3. **Conflict resolution for simultaneous sort parameters**: What should the system do if a caller supplies both `?lat=X&lon=Y` (distance sort) and a pickup-time sort parameter simultaneously? Options: (a) distance sort takes precedence silently, (b) pickup-time sort takes precedence silently, (c) return HTTP 400 requiring the caller to choose one. A deterministic rule is required (see BR-007).

4. **Default sort order**: When no sort parameter is supplied to the Ride list endpoint, what is the expected default ordering? Pickup time ascending, pickup time descending, or insertion order? This affects pagination stability.

5. **Authentication mechanism**: The spec mandates that only admin users can call endpoints but does not specify the authentication protocol. Should the system use Django's session-based authentication, token authentication (DRF `TokenAuthentication`), or JWT? The choice affects how API clients obtain credentials and how the admin role check is enforced in middleware/permissions.

6. **Pagination style**: Should the Ride list use offset/page-number pagination (e.g., `?page=2`) or cursor-based pagination? Cursor-based is more consistent with large datasets and distance sorting, but offset pagination is simpler. The constraint that "pagination must work with sorting" is easier to satisfy with cursor pagination for distance sort.

7. **Email uniqueness on User**: Is `email` a unique field on the `User` model? If two users share an email, filtering by rider email in the Ride list endpoint would return rides for multiple users. This needs to be a hard constraint if rider-email filtering is to be deterministic.

8. **RideEvent cascade behavior**: If a `Ride` is deleted, should its associated `RideEvents` be cascade-deleted? The reverse FK relationship needs an explicit `on_delete` policy documented before schema implementation.

9. **User deletion protection**: If a `User` is deleted while referenced as a rider or driver on existing rides, what should happen? Options: (a) `PROTECT` — block deletion, (b) `SET_NULL` — nullify FK (requires nullable FK), (c) `CASCADE` — delete rides too. This is a critical data integrity decision.

10. **Coordinate validation**: Should `pickup_latitude`, `pickup_longitude`, `dropoff_latitude`, and `dropoff_longitude` be validated for geographic range (latitude: -90 to 90, longitude: -180 to 180) at the API layer, or is raw float storage without range validation acceptable?

---

## Glossary

| Term | Definition |
|---|---|
| **DRF** | Django REST Framework — a toolkit for building Web APIs on top of Django |
| **ViewSet** | A DRF class that combines the logic for multiple related views (list, create, retrieve, update, destroy) into a single class |
| **Serializer** | A DRF component that converts complex data types (querysets, model instances) to and from Python native types and JSON |
| **Prefetch** | Django ORM mechanism that executes a separate query to fetch related objects in bulk, avoiding N+1 query patterns |
| **N+1 Query Problem** | A performance anti-pattern where loading N records triggers N additional queries to fetch related data |
| **`todays_ride_events`** | A computed field in the Ride list response containing only RideEvents created within the last 24 hours |
| **Pickup coordinates** | The `pickup_latitude` and `pickup_longitude` fields on the `Ride` model representing where a rider is collected |
| **Dropoff coordinates** | The `dropoff_latitude` and `dropoff_longitude` fields on the `Ride` model representing where a rider is delivered |
| **Distance sort** | A sort mode on the Ride list endpoint that orders results by Euclidean or haversine distance from a caller-supplied GPS coordinate to each ride's pickup location |
| **Admin role** | A `User` record whose `role` field equals `'admin'`; the only user type permitted to call any API endpoint |
| **PII** | Personally Identifiable Information — data that can be used to identify an individual, such as email address or phone number |
| **COUNT query** | A SQL `SELECT COUNT(*)` query issued by DRF pagination backends to compute total result count for page navigation |
| **Annotation** | A Django ORM operation that adds a computed value to each object in a queryset, evaluated in the database (e.g., a distance calculation) |

---

[PHASE 1 COMPLETE - HANDING OFF TO TECHSOLUTION ENGINEER]
