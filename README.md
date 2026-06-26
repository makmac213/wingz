# Wingz Ride Management API

A production-quality Django REST Framework API for managing ride lifecycle data
— Users (riders and drivers), Rides, and RideEvents. Access is admin-only,
enforced globally via DRF Token Authentication and a custom `IsAdminRole`
permission. The Ride list endpoint delivers paginated, filterable,
multi-mode-sortable results with embedded related objects in a fixed query
budget (COUNT + data + prefetch = 3 queries) regardless of page size.

References: `docs/BRD.md`, `docs/techsolution.md`, `docs/implementation.md`,
`docs/test_plans.md`.

---

## Tech Stack

| Component | Choice |
|---|---|
| Language | Python 3.9+ (developed/tested on 3.9 and 3.11) |
| Framework | Django 4.2 LTS |
| API | Django REST Framework 3.14+ |
| Auth | DRF Token Authentication (`rest_framework.authtoken`) |
| Filtering | `django-filter` |
| Config | `python-decouple` |
| Dev DB | SQLite 3.38+ (trig functions required for distance sort) |
| Tests | `pytest` + `pytest-django` |

---

## Setup

```bash
# 1. Clone and enter the project
cd wingz

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) configure environment
cp .env.example .env              # adjust SECRET_KEY etc. as needed
# The project boots with safe dev defaults even without a .env file.

# 5. Apply migrations
python manage.py migrate

# 6. Seed demo data (2 admins, 3 riders/drivers, 10 rides + events)
python manage.py seed_data
# Prints a ready-to-use admin token and login.

# 7. Run the development server
python manage.py runserver
```

The API is then available at `http://127.0.0.1:8000/api/v1/`.

> **SQLite note:** the distance sort uses SQL trigonometric functions
> (`ACOS`, `COS`, `SIN`, `RADIANS`), which require **SQLite ≥ 3.38**. Check with
> `python -c "import sqlite3; print(sqlite3.sqlite_version)"`. PostgreSQL
> supports these natively in production.

---

## Authentication

All endpoints (except the token endpoint) require an admin token:

```
Authorization: Token <token_value>
```

### Obtaining a token

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin@wingz.dev", "password": "admin123"}'
# -> {"token": "9085a083bf54cc4b0014f81e6ea2683038c8dcc9"}
```

> The DRF token serializer's credential field is literally named `username`;
> because `USERNAME_FIELD = 'email'`, you pass the **email** as the `username`
> value. `seed_data` also prints a token directly for convenience.

### Using the token

```bash
curl http://127.0.0.1:8000/api/v1/rides/ \
  -H "Authorization: Token <token_value>"
```

- Missing/invalid token → **401 Unauthorized**
- Valid token, non-admin role → **403 Forbidden**

---

## API Endpoint Reference

Base URL: `/api/v1/`

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token/` | Obtain auth token (`username` = email, `password`) |

### Users

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/users/` | List users (paginated) | 200 |
| POST | `/users/` | Create user | 201 |
| GET | `/users/{id_user}/` | Retrieve user | 200 |
| PUT/PATCH | `/users/{id_user}/` | Update user | 200 |
| DELETE | `/users/{id_user}/` | Delete user (409 if referenced by rides) | 204 |

### Rides

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/rides/` | List rides (filter, sort, paginate) | 200 |
| POST | `/rides/` | Create ride | 201 |
| GET | `/rides/{id_ride}/` | Retrieve ride (full `ride_events`) | 200 |
| PUT/PATCH | `/rides/{id_ride}/` | Update ride | 200 |
| DELETE | `/rides/{id_ride}/` | Delete ride (cascades events) | 204 |

### Ride Events

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/events/` | List events (filter by `ride`) | 200 |
| POST | `/events/` | Create event | 201 |
| GET | `/events/{id_ride_event}/` | Retrieve event | 200 |
| PUT/PATCH | `/events/{id_ride_event}/` | Update event | 200 |
| DELETE | `/events/{id_ride_event}/` | Delete event | 204 |

---

## Ride List Query Parameters

| Parameter | Type | Description | Example |
|---|---|---|---|
| `status` | string | Filter by status (`en-route`/`pickup`/`dropoff`) | `?status=en-route` |
| `rider_email` | email | Filter by rider's email (case-insensitive) | `?rider_email=john@wingz.dev` |
| `lat` | float | Latitude for distance sort (**required with `lon`**) | `?lat=37.7749` |
| `lon` | float | Longitude for distance sort (**required with `lat`**) | `?lon=-122.4194` |
| `page` | int | Page number | `?page=2` |
| `page_size` | int | Items per page (max 100, default 20) | `?page_size=20` |

**Behavior notes**

- **Default sort:** `pickup_time` ascending (with `id_ride` as a stable
  tiebreaker).
- **Distance sort:** supplying both `lat` and `lon` sorts nearest-first using a
  database-level Haversine annotation. It takes precedence over time sort.
- Supplying only one of `lat`/`lon` returns **400**. Non-numeric or
  out-of-range coordinates return **400**.
- An invalid `status` or malformed `rider_email` returns **400**.
- `todays_ride_events` in the list response contains only events from the last
  24 hours, filtered at the SQL layer (never in Python).

### Example list response

```json
{
  "count": 10,
  "next": "http://127.0.0.1:8000/api/v1/rides/?page=2",
  "previous": null,
  "results": [
    {
      "id_ride": 42,
      "status": "en-route",
      "pickup_latitude": 37.7749,
      "pickup_longitude": -122.4194,
      "dropoff_latitude": 37.3382,
      "dropoff_longitude": -121.8863,
      "pickup_time": "2026-06-26T14:30:00Z",
      "id_rider": {
        "id_user": 5, "role": "rider", "first_name": "John",
        "last_name": "Doe", "email": "john@wingz.dev",
        "phone_number": "+14155550001"
      },
      "id_driver": {
        "id_user": 8, "role": "rider", "first_name": "Alice",
        "last_name": "Brown", "email": "alice@wingz.dev",
        "phone_number": "+14155550002"
      },
      "todays_ride_events": [
        {
          "id_ride_event": 101, "id_ride": 42,
          "description": "Status changed to pickup",
          "created_at": "2026-06-26T13:32:00Z"
        }
      ]
    }
  ]
}
```

The **detail** endpoint (`GET /rides/{id}/`) returns the full all-time
`ride_events` list instead of `todays_ride_events`.

---

## Architecture Highlights

- **Custom user model** (`rides.User`) extends `AbstractBaseUser` with PK
  `id_user`, `USERNAME_FIELD = 'email'`, and a domain `role` field
  (`admin`/`rider`). `AUTH_USER_MODEL` is set before the first migration.
- **2-query data ceiling** on the Ride list: `select_related('id_rider',
  'id_driver')` collapses the two user joins into the main query, and a
  `Prefetch` with a `created_at` predicate (`to_attr='todays_ride_events'`)
  loads recent events in a single batched query. With pagination's COUNT, the
  endpoint uses exactly 3 queries — flat regardless of page size.
- **DB-level distance sort:** a Haversine `ExpressionWrapper` built from
  `ACos`/`Cos`/`Sin`/`Radians` ORM functions, ordered as
  `order_by('distance', 'id_ride')` *before* slicing, so `LIMIT/OFFSET`
  operates on pre-sorted rows. All coordinate inputs are parameterized via
  `Value(...)` (no SQL injection surface).
- **Global security:** `DEFAULT_AUTHENTICATION_CLASSES` (Token) and
  `DEFAULT_PERMISSION_CLASSES` (`IsAdminRole`) are set at the settings level so
  no endpoint can accidentally bypass auth. `password` is write-only and never
  serialized.
- **Referential integrity:** `Ride.id_rider`/`id_driver` use `PROTECT`
  (deleting a referenced user returns **409**); `RideEvent.id_ride` uses
  `CASCADE`.

---

## Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=rides --cov-report=term-missing
pytest tests/test_query_count.py -v -s   # inspect SQL for the query-count gate
```

Test settings (`wingz/settings_test.py`) use an in-memory SQLite database and
fast password hashing.

> **Query-count tests** use a force-authenticated client so the measured window
> reflects the *endpoint's* query budget (COUNT + data + prefetch = 3). DRF
> Token Authentication adds one DB lookup per request to resolve the token →
> user; that auth cost is verified separately in `tests/test_permissions.py`
> and intentionally excluded from the 3-query endpoint budget.

---

## Bonus: Long-Duration Trips Analytical Query

Finds rides whose duration (from the `pickup` event to the `dropoff` event)
exceeds 1 hour, grouped by calendar month and driver. Duration is computed from
`RideEvent` timestamps — there is no `dropoff_time` column on `Ride`.

### SQLite (development)

```sql
WITH pickup_events AS (
    SELECT id_ride_id, created_at AS pickup_time
    FROM rides_rideevent
    WHERE description = 'Status changed to pickup'
),
dropoff_events AS (
    SELECT id_ride_id, created_at AS dropoff_time
    FROM rides_rideevent
    WHERE description = 'Status changed to dropoff'
),
trip_durations AS (
    SELECT
        r.id_ride,
        r.id_driver_id,
        p.pickup_time,
        d.dropoff_time,
        (JULIANDAY(d.dropoff_time) - JULIANDAY(p.pickup_time)) * 24 AS duration_hours
    FROM rides_ride r
    JOIN pickup_events  p ON p.id_ride_id = r.id_ride
    JOIN dropoff_events d ON d.id_ride_id = r.id_ride
    WHERE (JULIANDAY(d.dropoff_time) - JULIANDAY(p.pickup_time)) * 24 > 1
)
SELECT
    strftime('%Y-%m', pickup_time)                  AS month,
    u.first_name || ' ' || substr(u.last_name, 1, 1) AS driver,
    COUNT(*)                                        AS count_of_trips_over_1hr
FROM trip_durations td
JOIN rides_user u ON u.id_user = td.id_driver_id
GROUP BY month, driver
ORDER BY month, driver;
```

### PostgreSQL / MySQL (production variant)

Replace the SQLite-specific date math:

- `strftime('%Y-%m', pickup_time)` → `TO_CHAR(pickup_time, 'YYYY-MM')`
  (PostgreSQL) or `DATE_FORMAT(pickup_time, '%Y-%m')` (MySQL).
- `(JULIANDAY(d.dropoff_time) - JULIANDAY(p.pickup_time)) * 24` →
  `EXTRACT(EPOCH FROM (d.dropoff_time - p.pickup_time)) / 3600.0` (PostgreSQL)
  or `TIMESTAMPDIFF(SECOND, p.pickup_time, d.dropoff_time) / 3600.0` (MySQL).

---

## Project Structure

```
wingz/
├── manage.py
├── requirements.txt
├── .env.example
├── pytest.ini
├── README.md
├── wingz/                 # Django project config
│   ├── settings.py
│   ├── settings_test.py
│   ├── urls.py
│   └── wsgi.py
├── rides/                 # Main app
│   ├── models.py          # User, Ride, RideEvent
│   ├── serializers.py
│   ├── views.py           # ViewSets, token view, exception handler
│   ├── permissions.py     # IsAdminRole
│   ├── filters.py
│   ├── pagination.py
│   ├── urls.py
│   ├── management/commands/seed_data.py
│   └── migrations/
└── tests/                 # pytest suite
```
