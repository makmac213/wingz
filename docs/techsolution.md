# Technical Solution Document
## Wingz Ride Management API — Django REST Framework

**Document ID:** TSD-2026-001
**Date:** 2026-06-26
**Status:** Approved for Implementation
**References:** BRD-2026-001

---

## Assumptions (Resolved Open Questions)

The following open questions from the BRD are resolved here before design begins:

| # | Question | Resolution |
|---|---|---|
| 1 | Dropoff time for bonus SQL | Duration computed from RideEvent timestamps where description = `'Status changed to pickup'` and `'Status changed to dropoff'`. No `dropoff_time` field added to `Ride`. |
| 2 | Non-admin role value | The role field uses three choices: `'admin'`, `'rider'`, and `'driver'`. Riders and drivers are distinct roles. A user assigned as `id_driver` on a Ride must have `role='driver'`; a user assigned as `id_rider` must have `role='rider'`. |
| 3 | Simultaneous sort parameters | Distance sort (`lat`/`lon`) takes precedence silently over pickup-time sort. If only pickup-time sort is specified, it is used. Default is pickup-time ascending. |
| 4 | Default sort order | `pickup_time` ascending when no sort parameter is supplied. |
| 5 | Authentication mechanism | DRF Token Authentication (`rest_framework.authtoken`). Chosen over JWT for simplicity — no refresh-token complexity, easy to layer JWT on later via `djangorestframework-simplejwt`. |
| 6 | Pagination style | Page-number pagination (`?page=N&page_size=M`). Cursor pagination is deferred — offset pagination is correct when `ORDER BY` is stable, which is guaranteed by our annotation approach. |
| 7 | Email uniqueness | `email` is unique on `User`. Required for deterministic rider-email filtering. |
| 8 | RideEvent cascade | `CASCADE` on `RideEvent.id_ride` — deleting a ride removes its events. Documented business rule. |
| 9 | User deletion protection | `PROTECT` on `Ride.id_rider` and `Ride.id_driver`. A `User` referenced on any ride cannot be deleted. Returns HTTP 409 (handled in view). |
| 10 | Coordinate validation | Latitude range -90 to 90, longitude range -180 to 180 validated at serializer layer. |

---

## Overview

Wingz requires a production-quality RESTful API to manage ride lifecycle data — Users (riders and drivers), Rides, and RideEvents. The system enforces admin-only access via DRF Token Authentication and a custom `IsAdminRole` permission class. The central engineering challenge is the Ride list endpoint, which must deliver paginated, filterable, multi-mode sortable results with embedded related objects in no more than 2 SQL data queries, using Django ORM's `select_related`, `Prefetch`, and database-level annotation for distance sorting.

---

## Goals and Non-Goals

### Goals
- Full CRUD REST API for `User`, `Ride`, and `RideEvent` entities.
- Admin-only access enforced globally via `IsAdminRole` permission.
- Ride list endpoint: filter by `status` and `rider_email`, sort by `pickup_time` or distance-from-coordinate, paginated, max 2 SQL data queries.
- `todays_ride_events` field filtered at the SQL layer via `Prefetch` with date predicate.
- Distance sort via DB-level Haversine annotation (`ExpressionWrapper` + trigonometric ORM functions).
- Bonus analytical SQL query for long-duration trips.
- Structured JSON error responses for all error conditions.
- Required database indexes documented and applied.

### Non-Goals
- End-user (non-admin) auth flows, registration, password management.
- Real-time features (WebSocket, push notifications).
- Frontend or mobile clients.
- Payment, fare calculation, GPS tracking, or dispatch logic.
- Third-party integrations (maps, routing, OAuth providers).
- Soft-delete, archival, or audit trail beyond `RideEvent`.
- Docker / CI/CD infrastructure.
- Automated test framework setup (test plan documented, implementation deferred per BRD scope).

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        API Client (Admin)                    │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTPS / JSON
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Django Application                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  urls.py  (DRF DefaultRouter)                       │   │
│  │  /api/users/        /api/rides/      /api/events/   │   │
│  └───────────────────┬─────────────────────────────────┘   │
│                      │                                      │
│  ┌───────────────────▼─────────────────────────────────┐   │
│  │  Authentication Layer                               │   │
│  │  TokenAuthentication (DRF authtoken)                │   │
│  │  IsAdminRole (custom DRF Permission)                │   │
│  └───────────────────┬─────────────────────────────────┘   │
│                      │                                      │
│  ┌───────────────────▼─────────────────────────────────┐   │
│  │  ViewSets (views.py)                                │   │
│  │  UserViewSet  │  RideViewSet  │  RideEventViewSet   │   │
│  └───────────────────┬─────────────────────────────────┘   │
│                      │                                      │
│  ┌───────────────────▼─────────────────────────────────┐   │
│  │  Serializers (serializers.py)                       │   │
│  │  UserSerializer                                     │   │
│  │  RideListSerializer  │  RideDetailSerializer        │   │
│  │  RideEventSerializer                                │   │
│  └───────────────────┬─────────────────────────────────┘   │
│                      │                                      │
│  ┌───────────────────▼─────────────────────────────────┐   │
│  │  Query Layer (get_queryset)                         │   │
│  │  select_related('id_rider', 'id_driver')            │   │
│  │  Prefetch('rideevent_set', filtered, to_attr=...)   │   │
│  │  annotate(distance=ExpressionWrapper(...))          │   │
│  │  filter(status=..., id_rider__email=...)            │   │
│  │  order_by('pickup_time' | 'distance')               │   │
│  └───────────────────┬─────────────────────────────────┘   │
│                      │                                      │
│  ┌───────────────────▼─────────────────────────────────┐   │
│  │  Django ORM → SQLite (dev) / PostgreSQL (prod)      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | Choice | Justification |
|---|---|---|
| Language | Python 3.11+ | LTS, full Django 4.x support, type hints mature |
| Web Framework | Django 4.2 LTS | LTS release, stable ORM, excellent DRF integration |
| API Framework | Django REST Framework 3.14+ | Industry standard for Django APIs; ViewSets, Serializers, Pagination built-in |
| Authentication | `rest_framework.authtoken` (DRF Token Auth) | Stateless, simple, no refresh complexity; can be swapped for JWT later |
| Dev Database | SQLite 3 | Zero-config for development; Haversine approximation via ORM trig functions |
| Prod Database | PostgreSQL 15+ | ACID, indexing, `EXPLAIN ANALYZE`, `DATE_TRUNC` for bonus SQL |
| Filtering | `django-filter` 23+ | Declarative filter backends; integrates natively with DRF ViewSets |
| Environment | `python-decouple` or `django-environ` | Separate config from code; manage `SECRET_KEY`, `DATABASE_URL` |
| Testing | `pytest-django` | Faster than Django's built-in test runner; fixtures, parametrize |
| Dev Tools | `django-extensions` (optional) | `shell_plus`, `sqldiff` for schema inspection |

---

## Key Design Decisions

### 1. Custom User Model (Standalone, not AbstractUser)

**Decision:** The `User` model uses a custom primary key `id_user` and does not extend `AbstractUser`. Instead it extends `AbstractBaseUser` with a custom manager.

**Rationale:** The BRD specifies `id_user` as the PK and a `role` field (not `is_staff`/`is_superuser`). Extending `AbstractUser` would inherit 15+ unused fields and create confusion. `AbstractBaseUser` gives password hashing and authentication backend hooks without the baggage. The `AUTH_USER_MODEL` setting points to our custom model.

**Impact:** `settings.AUTH_USER_MODEL = 'rides.User'` must be set before the first migration. All `request.user` references resolve to our custom `User` instance.

### 2. DRF Token Authentication over JWT

**Decision:** Use `rest_framework.authtoken.TokenAuthentication`.

**Rationale:** The assessment does not require stateless horizontal scaling or token expiry. Token auth is simpler to reason about, requires one extra table (`authtoken_token`), and can be swapped for JWT by changing `DEFAULT_AUTHENTICATION_CLASSES` without model changes.

**Future path:** Replace with `djangorestframework-simplejwt` by adding `JWTAuthentication` to `DEFAULT_AUTHENTICATION_CLASSES` and exposing `/api/token/` and `/api/token/refresh/` endpoints.

### 3. IsAdminRole Custom Permission

**Decision:** A DRF `BasePermission` subclass that checks `request.user.role == 'admin'`. Applied globally via `DEFAULT_PERMISSION_CLASSES`.

**Rationale:** Django's `is_staff` flag is conceptually different from a domain-level `role` field. Keeping permission logic in a named class makes it testable and replaceable without touching views.

### 4. Ride List Query Strategy: select_related + Prefetch

**Decision:** Use `select_related('id_rider', 'id_driver')` for the two FK User joins (produces a single SQL JOIN) and a `Prefetch` object with a filtered queryset for `todays_ride_events`.

**Rationale:** This yields exactly 2 SQL queries for data:
- Query 1 (paginated): `SELECT ride.*, rider.*, driver.* FROM rides JOIN users AS rider ... JOIN users AS driver ... WHERE ... ORDER BY ... LIMIT N OFFSET M`
- Query 2 (prefetch): `SELECT * FROM ride_events WHERE id_ride IN (...) AND created_at >= <24h-ago>`

The `Prefetch` with `to_attr='todays_ride_events'` stores filtered events on each `Ride` instance as a Python list attribute. The serializer reads `instance.todays_ride_events` directly without triggering additional queries.

### 5. Distance Sort via Database Annotation (Haversine)

**Decision:** Annotate the queryset with a computed `distance` field using Django ORM math functions (`ACos`, `Sin`, `Cos`, `Radians`). `ORDER BY distance` is then applied before slicing, ensuring `LIMIT`/`OFFSET` pagination operates on the pre-sorted result.

**Rationale:** In-memory distance sort after DB fetch would require loading all rows before pagination — defeating the purpose of DB-level pagination. The annotation is computed per-row at the DB layer, allowing `ORDER BY distance LIMIT N OFFSET M` in a single SQL statement.

**SQLite caveat:** SQLite 3.38+ supports trigonometric functions. For older SQLite (< 3.38), a Euclidean approximation (`sqrt((lat2-lat1)^2 + (lon2-lon1)^2)`) can be used for dev. Document this difference clearly.

**PostgreSQL prod:** The same Haversine annotation works. PostGIS `ST_Distance` is more accurate for great-circle distances but requires the PostGIS extension; the Haversine ORM annotation is sufficient for sorting purposes.

### 6. Page-Number Pagination

**Decision:** Use `PageNumberPagination` with configurable `page_size` (default 20, max 100).

**Rationale:** Cursor pagination is more complex to implement, especially with the distance annotation (cursor encoding requires serializing the distance value). Page-number pagination is stable when `ORDER BY` includes a unique column as a tiebreaker. We add `id_ride` as a secondary sort key to guarantee stable pagination.

### 7. RideEvent Cascade / User Protect

**Decision:**
- `RideEvent.id_ride`: `on_delete=CASCADE` — events are child records of rides.
- `Ride.id_rider` and `Ride.id_driver`: `on_delete=PROTECT` — prevents silent data loss.

**Rationale:** Users in the real world are operational entities that may be deactivated rather than deleted. `PROTECT` forces the caller to handle the dependency explicitly.

---

## Data Models / Schema

### User

```sql
CREATE TABLE rides_user (
    id_user        INTEGER PRIMARY KEY AUTOINCREMENT,  -- SERIAL in PostgreSQL
    role           VARCHAR(20) NOT NULL,               -- CHECK (role IN ('admin','rider','driver'))
    first_name     VARCHAR(150) NOT NULL,
    last_name      VARCHAR(150) NOT NULL,
    email          VARCHAR(254) NOT NULL UNIQUE,
    phone_number   VARCHAR(30) NOT NULL,
    password       VARCHAR(128) NOT NULL,              -- AbstractBaseUser hashed password
    last_login     DATETIME NULL
);

CREATE INDEX idx_user_email ON rides_user(email);
CREATE INDEX idx_user_role  ON rides_user(role);
```

### Ride

```sql
CREATE TABLE rides_ride (
    id_ride            INTEGER PRIMARY KEY AUTOINCREMENT,
    status             VARCHAR(20) NOT NULL,  -- CHECK (status IN ('en-route','pickup','dropoff'))
    id_rider_id        INTEGER NOT NULL REFERENCES rides_user(id_user) ON DELETE RESTRICT,
    id_driver_id       INTEGER NOT NULL REFERENCES rides_user(id_user) ON DELETE RESTRICT,
    pickup_latitude    FLOAT NOT NULL,
    pickup_longitude   FLOAT NOT NULL,
    dropoff_latitude   FLOAT NOT NULL,
    dropoff_longitude  FLOAT NOT NULL,
    pickup_time        DATETIME NOT NULL
);

CREATE INDEX idx_ride_status      ON rides_ride(status);
CREATE INDEX idx_ride_pickup_time ON rides_ride(pickup_time);
CREATE INDEX idx_ride_id_rider    ON rides_ride(id_rider_id);
CREATE INDEX idx_ride_id_driver   ON rides_ride(id_driver_id);
```

**Note on Django FK column naming:** Django appends `_id` to FK field names by default. Since the model field is `id_rider` (a FK), Django stores it as column `id_rider_id`. This is consistent with the BRD's `id_rider` FK naming convention and Django's ORM conventions simultaneously.

### RideEvent

```sql
CREATE TABLE rides_rideevent (
    id_ride_event  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ride_id     INTEGER NOT NULL REFERENCES rides_ride(id_ride) ON DELETE CASCADE,
    description    VARCHAR(255) NOT NULL,
    created_at     DATETIME NOT NULL
);

CREATE INDEX idx_rideevent_id_ride    ON rides_rideevent(id_ride_id);
CREATE INDEX idx_rideevent_created_at ON rides_rideevent(created_at);
-- Composite index for the Prefetch filter pattern
CREATE INDEX idx_rideevent_ride_created ON rides_rideevent(id_ride_id, created_at);
```

### Token (DRF AuthToken — auto-created by `rest_framework.authtoken`)

```sql
CREATE TABLE authtoken_token (
    key         VARCHAR(40) PRIMARY KEY,
    created     DATETIME NOT NULL,
    user_id     INTEGER NOT NULL UNIQUE REFERENCES rides_user(id_user) ON DELETE CASCADE
);
```

---

## Django Model Definitions (Reference)

```python
# rides/models.py

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    ROLE_CHOICES = [('admin', 'Admin'), ('rider', 'Rider'), ('driver', 'Driver')]

    id_user      = models.AutoField(primary_key=True)
    role         = models.CharField(max_length=20, choices=ROLE_CHOICES)
    first_name   = models.CharField(max_length=150)
    last_name    = models.CharField(max_length=150)
    email        = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=30)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'role', 'phone_number']

    objects = UserManager()

    class Meta:
        db_table = 'rides_user'
        indexes = [
            models.Index(fields=['role']),
        ]


class Ride(models.Model):
    STATUS_CHOICES = [
        ('en-route', 'En Route'),
        ('pickup',   'Pickup'),
        ('dropoff',  'Dropoff'),
    ]

    id_ride            = models.AutoField(primary_key=True)
    status             = models.CharField(max_length=20, choices=STATUS_CHOICES)
    id_rider           = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='rides_as_rider'
    )
    id_driver          = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='rides_as_driver'
    )
    pickup_latitude    = models.FloatField()
    pickup_longitude   = models.FloatField()
    dropoff_latitude   = models.FloatField()
    dropoff_longitude  = models.FloatField()
    pickup_time        = models.DateTimeField()

    class Meta:
        db_table = 'rides_ride'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['pickup_time']),
            models.Index(fields=['id_rider']),
            models.Index(fields=['id_driver']),
        ]


class RideEvent(models.Model):
    id_ride_event = models.AutoField(primary_key=True)
    id_ride       = models.ForeignKey(
        Ride, on_delete=models.CASCADE, related_name='events'
    )
    description   = models.CharField(max_length=255)
    created_at    = models.DateTimeField()

    class Meta:
        db_table = 'rides_rideevent'
        indexes = [
            models.Index(fields=['id_ride', 'created_at']),
            models.Index(fields=['created_at']),
        ]
```

---

## API Contracts

### Base URL
```
/api/v1/
```

### Authentication
All endpoints require:
```
Authorization: Token <token_value>
```
Tokens are obtained via:
```
POST /api/v1/auth/token/
Body: { "email": "admin@example.com", "password": "secret" }
Response 200: { "token": "abc123..." }
```

### Global Error Shapes

```json
// 401 Unauthorized
{ "detail": "Authentication credentials were not provided." }

// 403 Forbidden
{ "detail": "You do not have permission to perform this action." }

// 400 Bad Request (field validation)
{ "field_name": ["Error message."] }

// 400 Bad Request (query param validation)
{ "error": "lat and lon must both be provided for distance sorting." }

// 404 Not Found
{ "detail": "Not found." }
```

---

### User Endpoints

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/api/v1/users/` | List all users (paginated) | 200 |
| POST | `/api/v1/users/` | Create user | 201 |
| GET | `/api/v1/users/{id_user}/` | Retrieve user | 200 |
| PUT | `/api/v1/users/{id_user}/` | Full update | 200 |
| PATCH | `/api/v1/users/{id_user}/` | Partial update | 200 |
| DELETE | `/api/v1/users/{id_user}/` | Delete user | 204 |

**User object:**
```json
{
  "id_user": 1,
  "role": "admin",
  "first_name": "Jane",
  "last_name": "Smith",
  "email": "jane@example.com",
  "phone_number": "+14155551234"
}
```

Note: `password` is write-only; never returned in responses.

---

### Ride Endpoints

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/api/v1/rides/` | List rides (filtered, sorted, paginated) | 200 |
| POST | `/api/v1/rides/` | Create ride | 201 |
| GET | `/api/v1/rides/{id_ride}/` | Retrieve ride (full events) | 200 |
| PUT | `/api/v1/rides/{id_ride}/` | Full update | 200 |
| PATCH | `/api/v1/rides/{id_ride}/` | Partial update | 200 |
| DELETE | `/api/v1/rides/{id_ride}/` | Delete ride | 204 |

**Ride List Query Parameters:**

| Parameter | Type | Description | Example |
|---|---|---|---|
| `status` | string | Filter by ride status | `?status=en-route` |
| `rider_email` | email | Filter by rider's email | `?rider_email=jane@example.com` |
| `sort` | string | Sort mode: `pickup_time` (default) or `distance` | `?sort=pickup_time` |
| `lat` | float | Latitude for distance sort (required with `lon`) | `?lat=37.7749` |
| `lon` | float | Longitude for distance sort (required with `lat`) | `?lon=-122.4194` |
| `page` | int | Page number | `?page=2` |
| `page_size` | int | Items per page (max 100) | `?page_size=20` |

**Ride List response envelope:**
```json
{
  "count": 1523,
  "next": "http://api/v1/rides/?page=3",
  "previous": "http://api/v1/rides/?page=1",
  "results": [ /* Ride objects */ ]
}
```

**Ride List object:**
```json
{
  "id_ride": 42,
  "status": "en-route",
  "pickup_latitude": 37.7749,
  "pickup_longitude": -122.4194,
  "dropoff_latitude": 37.3382,
  "dropoff_longitude": -121.8863,
  "pickup_time": "2026-06-26T14:30:00Z",
  "id_rider": {
    "id_user": 5,
    "role": "rider",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone_number": "+14155550001"
  },
  "id_driver": {
    "id_user": 8,
    "role": "driver",
    "first_name": "Alice",
    "last_name": "Brown",
    "email": "alice@example.com",
    "phone_number": "+14155550002"
  },
  "todays_ride_events": [
    {
      "id_ride_event": 101,
      "id_ride": 42,
      "description": "Status changed to en-route",
      "created_at": "2026-06-26T14:32:00Z"
    }
  ]
}
```

**Ride Detail object** (same as above, but `todays_ride_events` replaced by full `ride_events`):
```json
{
  "id_ride": 42,
  "...": "...",
  "ride_events": [
    { "id_ride_event": 99, "description": "Status changed to en-route", "created_at": "2026-06-25T10:00:00Z" },
    { "id_ride_event": 101, "description": "Status changed to pickup", "created_at": "2026-06-26T14:32:00Z" }
  ]
}
```

---

### RideEvent Endpoints

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/api/v1/events/` | List events (optionally filter by ride) | 200 |
| POST | `/api/v1/events/` | Create event | 201 |
| GET | `/api/v1/events/{id_ride_event}/` | Retrieve event | 200 |
| PUT | `/api/v1/events/{id_ride_event}/` | Full update | 200 |
| PATCH | `/api/v1/events/{id_ride_event}/` | Partial update | 200 |
| DELETE | `/api/v1/events/{id_ride_event}/` | Delete event | 204 |

**RideEvent List Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ride` | int | Filter by `id_ride` |

**RideEvent object:**
```json
{
  "id_ride_event": 101,
  "id_ride": 42,
  "description": "Status changed to en-route",
  "created_at": "2026-06-26T14:32:00Z"
}
```

---

### Token Endpoint

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/token/` | Obtain auth token |

---

## Critical Query Patterns

### Ride List — 2-Query Strategy

**Query 1 (COUNT — pagination):**
```sql
SELECT COUNT(*) FROM rides_ride
LEFT JOIN rides_user rider ON rides_ride.id_rider_id = rider.id_user
WHERE rides_ride.status = 'en-route';
```

**Query 2 (Data — with JOINs, annotation, ordering, pagination):**
```sql
SELECT
    r.*,
    rider.id_user, rider.role, rider.first_name, rider.last_name, rider.email, rider.phone_number,
    driver.id_user, driver.role, driver.first_name, driver.last_name, driver.email, driver.phone_number,
    (
      6371 * ACOS(
        COS(RADIANS(37.7749)) * COS(RADIANS(r.pickup_latitude))
        * COS(RADIANS(r.pickup_longitude) - RADIANS(-122.4194))
        + SIN(RADIANS(37.7749)) * SIN(RADIANS(r.pickup_latitude))
      )
    ) AS distance
FROM rides_ride r
JOIN rides_user rider  ON r.id_rider_id  = rider.id_user
JOIN rides_user driver ON r.id_driver_id = driver.id_user
WHERE r.status = 'en-route'
ORDER BY distance ASC, r.id_ride ASC
LIMIT 20 OFFSET 0;
```

**Query 3 (Prefetch — today's events only):**
```sql
SELECT * FROM rides_rideevent
WHERE id_ride_id IN (42, 43, 44, ...) -- IDs from Query 2 result page
AND created_at >= '2026-06-25T14:30:00Z'; -- now() - 24 hours
```

### ORM Implementation (Key Snippet)

```python
from datetime import timedelta
from django.utils import timezone
from django.db.models import FloatField, ExpressionWrapper, F, Value
from django.db.models.functions import ACos, Cos, Sin, Radians
from django.db.models import Prefetch

def get_distance_annotation(lat, lon):
    return ExpressionWrapper(
        Value(6371.0) * ACos(
            Cos(Radians(Value(lat))) * Cos(Radians(F('pickup_latitude')))
            * Cos(Radians(F('pickup_longitude')) - Radians(Value(lon)))
            + Sin(Radians(Value(lat))) * Sin(Radians(F('pickup_latitude')))
        ),
        output_field=FloatField()
    )

def get_ride_list_queryset(params):
    now = timezone.now()
    cutoff = now - timedelta(hours=24)

    todays_events_prefetch = Prefetch(
        'events',
        queryset=RideEvent.objects.filter(created_at__gte=cutoff),
        to_attr='todays_ride_events'
    )

    qs = Ride.objects.select_related('id_rider', 'id_driver') \
                     .prefetch_related(todays_events_prefetch)

    # Filters
    if params.get('status'):
        qs = qs.filter(status=params['status'])
    if params.get('rider_email'):
        qs = qs.filter(id_rider__email=params['rider_email'])

    # Sort
    if params.get('lat') and params.get('lon'):
        qs = qs.annotate(distance=get_distance_annotation(
            params['lat'], params['lon']
        )).order_by('distance', 'id_ride')
    else:
        qs = qs.order_by('pickup_time', 'id_ride')

    return qs
```

---

## Bonus: Analytical SQL Query (FR-034, FR-035)

This query finds all rides whose duration from the pickup event to the dropoff event exceeds 1 hour, grouped by calendar month and driver.

```sql
-- PostgreSQL dialect (DATE_TRUNC, EXTRACT)
-- Assumes description values: 'Status changed to pickup' and 'Status changed to dropoff'

WITH pickup_events AS (
    SELECT
        re.id_ride_id,
        re.created_at AS pickup_event_time
    FROM rides_rideevent re
    WHERE re.description = 'Status changed to pickup'
),
dropoff_events AS (
    SELECT
        re.id_ride_id,
        re.created_at AS dropoff_event_time
    FROM rides_rideevent re
    WHERE re.description = 'Status changed to dropoff'
),
ride_durations AS (
    SELECT
        r.id_ride,
        r.id_driver_id,
        pe.pickup_event_time,
        de.dropoff_event_time,
        EXTRACT(EPOCH FROM (de.dropoff_event_time - pe.pickup_event_time)) / 3600.0 AS duration_hours
    FROM rides_ride r
    INNER JOIN pickup_events  pe ON pe.id_ride_id = r.id_ride
    INNER JOIN dropoff_events de ON de.id_ride_id = r.id_ride
    WHERE de.dropoff_event_time > pe.pickup_event_time
)
SELECT
    DATE_TRUNC('month', rd.pickup_event_time)  AS trip_month,
    u.id_user                                  AS driver_id,
    u.first_name || ' ' || u.last_name         AS driver_name,
    u.email                                    AS driver_email,
    COUNT(*)                                   AS long_trips_count,
    ROUND(AVG(rd.duration_hours)::NUMERIC, 2)  AS avg_duration_hours,
    ROUND(MAX(rd.duration_hours)::NUMERIC, 2)  AS max_duration_hours
FROM ride_durations rd
INNER JOIN rides_user u ON u.id_user = rd.id_driver_id
WHERE rd.duration_hours > 1
GROUP BY
    DATE_TRUNC('month', rd.pickup_event_time),
    u.id_user,
    u.first_name,
    u.last_name,
    u.email
ORDER BY
    trip_month DESC,
    long_trips_count DESC;
```

**SQLite equivalent** (replaces `DATE_TRUNC` and `EXTRACT EPOCH`):
```sql
-- Replace DATE_TRUNC('month', ...) with:
STRFTIME('%Y-%m', rd.pickup_event_time) AS trip_month
-- Replace EXTRACT(EPOCH FROM ...) / 3600 with:
(JULIANDAY(de.dropoff_event_time) - JULIANDAY(pe.pickup_event_time)) * 24 AS duration_hours
```

---

## Security Considerations

### Authentication
- Token Auth: tokens are opaque 40-character strings stored in `authtoken_token`. No expiry by default — document that tokens should be rotated on compromise.
- All endpoints are protected by DRF's `DEFAULT_AUTHENTICATION_CLASSES` and `DEFAULT_PERMISSION_CLASSES` at the settings level, not per-view, to prevent accidental bypass.

### Authorization
- `IsAdminRole` checks `request.user` is authenticated AND `request.user.role == 'admin'`. Both checks are required in the permission class.
- No user can escalate their own role via the API — the `role` field is writable only by admins (all endpoints are admin-only), but self-update should be reviewed to prevent self-promotion in production.

### Input Validation
- `status` field: Django `choices` constraint + DRF serializer validation. Invalid values return 400.
- Coordinate range: serializer `validate_pickup_latitude` etc. enforce -90/90 and -180/180 bounds.
- `lat`/`lon` query params: validated in the view's `get_queryset` before annotation; non-numeric values return 400.
- `rider_email`: basic email format validation via DRF before filter application.

### Data Protection
- `password` field is write-only (`write_only=True` on serializer). Never appears in responses.
- Error bodies do not echo PII from request inputs beyond field names.
- `phone_number` and `email` are only returned to authenticated admin users (all endpoints require admin auth).

### SQL Injection
- All queries use Django ORM parameterized expressions. The Haversine annotation uses `Value(lat)` and `Value(lon)` which are parameterized. No raw string interpolation in SQL.

---

## Scalability and Performance

### Indexes
All indexes are defined in the Django model `Meta.indexes` and applied via migrations:
- `rides_user.email` — unique, used for rider-email filter join
- `rides_ride.status` — used for status filter
- `rides_ride.pickup_time` — used for pickup-time sort
- `rides_ride.id_rider_id` — FK, used for join
- `rides_ride.id_driver_id` — FK, used for join
- `rides_rideevent.id_ride_id` + `created_at` (composite) — used by Prefetch filter
- `rides_rideevent.created_at` — used by Prefetch filter

### Query Count Ceiling
The 2-query ceiling on the Ride list is enforced by design: `select_related` eliminates per-ride FK lookups, `Prefetch` batches all event queries into one. This holds regardless of page size.

### Pagination
`PageNumberPagination` with `MAX_PAGE_SIZE = 100` prevents runaway result sets. The secondary sort key `id_ride` ensures stable pagination across identical `pickup_time` or `distance` values.

### Distance Sort
The Haversine annotation is computed per-row at the DB layer. For very large tables (tens of millions), a partial index on `pickup_time` and `status` will be needed to prevent full table scans before the `ORDER BY distance` step. PostGIS `ST_Distance` with a spatial index (`GIST`) is the production upgrade path for geographic queries at scale.

### Connection Pooling
For production PostgreSQL, use `django-db-geventpool` or configure `CONN_MAX_AGE` to avoid connection overhead.

---

## Dependencies and Risks

| Dependency | Risk | Mitigation |
|---|---|---|
| SQLite trig functions (dev) | SQLite < 3.38 lacks `ACOS`/`COS`/`SIN`/`RADIANS` | Pin SQLite version or use Euclidean approximation in dev with a feature flag |
| DRF `PageNumberPagination` count query | COUNT on large tables is slow | Add `count=False` or use `django-rest-framework-simplepagination` for infinite scroll if needed; for now, COUNT is acceptable per BRD |
| `AbstractBaseUser` custom model | Must be set before first migration; cannot be changed without resetting migrations | Set `AUTH_USER_MODEL` in `settings.py` before running `migrate` |
| `PROTECT` on User FK | DELETE `/api/v1/users/{id}/` returns 500 if not handled | Catch `ProtectedError` in `UserViewSet.destroy()` and return HTTP 409 |
| Haversine annotation + distance = NULL | When lat/lon annotation returns NULL (invalid coords stored in DB) | Add `output_field=FloatField()` and handle NULLs in ordering (place last) |
| `related_name='events'` on RideEvent FK | `Prefetch('events', ...)` must match this `related_name` exactly | Test confirmed in integration tests |
