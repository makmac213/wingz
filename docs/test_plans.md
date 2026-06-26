# Test Plans Document
## Wingz Ride Management API — Django REST Framework

**Document ID:** TST-2026-001
**Date:** 2026-06-26
**References:** TSD-2026-001, IMP-2026-001, BRD-2026-001

---

## Testing Strategy Overview

| Layer | Tool | Purpose |
|---|---|---|
| Unit | `pytest-django` + `unittest.mock` | Serializer validation logic, permission class logic, query builder helpers |
| Integration | `pytest-django` + `APIClient` | Full request/response cycle against SQLite in-memory test DB |
| Performance (Query Count) | `django.test.utils.override_settings` + `django.db.connection.queries` | Assert max query count on Ride list endpoint |
| Security | `APIClient` unauthenticated/non-admin scenarios | Auth and permission enforcement |
| Edge Cases | Parametrized `pytest` tests | Boundary values, empty results, conflicting params |

**Note (per BRD Out of Scope):** Automated test framework setup is documented here as a plan. The engineer is expected to implement the test suite based on this document. No load testing infrastructure (k6, JMeter) is mandated for the assessment; performance testing is done via query-count assertions using Django's query debug tooling.

---

## Test Environment Setup

### 1. Install Test Dependencies
```bash
pip install pytest pytest-django
```

### 2. `pytest.ini`
```ini
[pytest]
DJANGO_SETTINGS_MODULE = wingz.settings_test
python_files = tests/test_*.py
python_classes = Test*
python_functions = test_*
```

### 3. `wingz/settings_test.py`
```python
from wingz.settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Disable password hashing for faster tests
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Enable query logging for query count tests
DEBUG = True
```

### 4. Shared Fixtures (`conftest.py`)

```python
# tests/conftest.py

import pytest
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from rides.models import User, Ride, RideEvent
from django.utils import timezone
from datetime import timedelta


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email='admin@test.com',
        password='admin123',
        role='admin',
        first_name='Admin',
        last_name='User',
        phone_number='+10000000001',
    )


@pytest.fixture
def rider_user(db):
    return User.objects.create_user(
        email='rider@test.com',
        password='rider123',
        role='rider',
        first_name='Rider',
        last_name='One',
        phone_number='+10000000002',
    )


@pytest.fixture
def driver_user(db):
    return User.objects.create_user(
        email='driver@test.com',
        password='driver123',
        role='rider',
        first_name='Driver',
        last_name='One',
        phone_number='+10000000003',
    )


@pytest.fixture
def admin_token(admin_user):
    token, _ = Token.objects.get_or_create(user=admin_user)
    return token.key


@pytest.fixture
def authenticated_client(api_client, admin_token):
    api_client.credentials(HTTP_AUTHORIZATION=f'Token {admin_token}')
    return api_client


@pytest.fixture
def sample_ride(db, rider_user, driver_user):
    return Ride.objects.create(
        status='en-route',
        id_rider=rider_user,
        id_driver=driver_user,
        pickup_latitude=37.7749,
        pickup_longitude=-122.4194,
        dropoff_latitude=37.3382,
        dropoff_longitude=-121.8863,
        pickup_time=timezone.now(),
    )


@pytest.fixture
def todays_event(db, sample_ride):
    return RideEvent.objects.create(
        id_ride=sample_ride,
        description='Status changed to en-route',
        created_at=timezone.now() - timedelta(hours=1),
    )


@pytest.fixture
def old_event(db, sample_ride):
    return RideEvent.objects.create(
        id_ride=sample_ride,
        description='Status changed to pickup',
        created_at=timezone.now() - timedelta(hours=25),
    )
```

### 5. Directory Structure

```
tests/
├── conftest.py
├── test_permissions.py
├── test_user_endpoints.py
├── test_ride_list.py
├── test_ride_crud.py
├── test_ride_event_endpoints.py
├── test_serializers.py
└── test_query_count.py
```

### 6. Run Tests
```bash
pytest tests/ -v
pytest tests/ -v --tb=short  # less verbose tracebacks
pytest tests/test_query_count.py -v -s  # see SQL output
```

---

## Unit Tests

### `tests/test_permissions.py` — IsAdminRole

| Test Case | Input | Expected Output |
|---|---|---|
| `test_unauthenticated_denied` | `AnonymousUser` | `has_permission` returns `False` |
| `test_rider_role_denied` | `User(role='rider')` | `has_permission` returns `False` |
| `test_admin_role_allowed` | `User(role='admin')` | `has_permission` returns `True` |
| `test_none_role_denied` | `User(role=None)` | `has_permission` returns `False` |
| `test_empty_role_denied` | `User(role='')` | `has_permission` returns `False` |

```python
# tests/test_permissions.py

import pytest
from unittest.mock import MagicMock
from rides.permissions import IsAdminRole


def make_request(user):
    request = MagicMock()
    request.user = user
    return request


@pytest.mark.parametrize('role,expected', [
    ('admin', True),
    ('rider', False),
    (None, False),
    ('', False),
])
def test_admin_role_permission(role, expected):
    permission = IsAdminRole()
    user = MagicMock()
    user.is_authenticated = True
    user.role = role
    request = make_request(user)
    assert permission.has_permission(request, None) == expected


def test_unauthenticated_user_denied():
    permission = IsAdminRole()
    user = MagicMock()
    user.is_authenticated = False
    request = make_request(user)
    assert permission.has_permission(request, None) is False
```

**Pass Criteria:** All 5 parametrized permission tests pass.

---

### `tests/test_serializers.py` — Serializer Validation

| Test Case | Input | Expected Output |
|---|---|---|
| `test_user_serializer_password_not_in_output` | Valid user data | `password` absent from serialized output |
| `test_user_invalid_role` | `role='superuser'` | `ValidationError` on `role` field |
| `test_ride_invalid_status` | `status='cancelled'` | `ValidationError` on `status` field |
| `test_ride_latitude_out_of_range` | `pickup_latitude=91.0` | `ValidationError` on `pickup_latitude` |
| `test_ride_longitude_out_of_range` | `pickup_longitude=181.0` | `ValidationError` on `pickup_longitude` |
| `test_ride_latitude_boundary_min` | `pickup_latitude=-90.0` | Valid, no error |
| `test_ride_latitude_boundary_max` | `pickup_latitude=90.0` | Valid, no error |
| `test_ride_longitude_boundary_min` | `pickup_longitude=-180.0` | Valid, no error |
| `test_ride_longitude_boundary_max` | `pickup_longitude=180.0` | Valid, no error |
| `test_ride_nonexistent_rider` | `id_rider=99999` | `ValidationError` on `id_rider` field |
| `test_ride_list_serializer_includes_todays_events` | Ride with prefetched `todays_ride_events` attr | Field present in output |
| `test_ride_detail_serializer_includes_ride_events` | Ride with `events` relation | `ride_events` field present |

**Pass Criteria:** All serializer validation tests pass; `password` never appears in output.

---

## Integration Tests

### `tests/test_permissions.py` — API Auth Enforcement

| Test Case | Setup | Expected HTTP |
|---|---|---|
| `test_list_users_unauthenticated` | No `Authorization` header | 401 |
| `test_list_users_non_admin_token` | Token for `role='rider'` user | 403 |
| `test_list_users_admin_token` | Token for `role='admin'` user | 200 |
| `test_list_rides_unauthenticated` | No header | 401 |
| `test_list_events_unauthenticated` | No header | 401 |
| `test_create_user_unauthenticated` | No header | 401 |
| `test_delete_ride_non_admin` | Rider token | 403 |

```python
# tests/test_permissions.py (integration portion)

@pytest.mark.django_db
def test_list_users_unauthenticated(api_client):
    response = api_client.get('/api/v1/users/')
    assert response.status_code == 401
    assert 'application/json' in response['Content-Type']


@pytest.mark.django_db
def test_list_users_non_admin(api_client, rider_user):
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=rider_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    response = api_client.get('/api/v1/users/')
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_users_admin(authenticated_client, admin_user):
    response = authenticated_client.get('/api/v1/users/')
    assert response.status_code == 200
```

**Pass Criteria:** All auth/permission tests return correct HTTP codes and JSON content-type.

---

### `tests/test_user_endpoints.py` — User CRUD

| Test Case | Expected HTTP | Expected Behavior |
|---|---|---|
| `test_create_user_valid` | 201 | User persisted; response includes `id_user`; `password` absent |
| `test_create_user_duplicate_email` | 400 | `email` field error returned |
| `test_create_user_invalid_role` | 400 | `role` field error returned |
| `test_create_user_missing_required_field` | 400 | Field-level error for missing field |
| `test_retrieve_user` | 200 | Correct user object returned |
| `test_retrieve_nonexistent_user` | 404 | `{"detail": "Not found."}` |
| `test_update_user_partial` | 200 | Only specified field updated |
| `test_update_user_full` | 200 | All fields updated |
| `test_delete_user_no_rides` | 204 | User deleted |
| `test_delete_user_with_rides` | 409 | `{"error": "..."}` with conflict message |
| `test_list_users_paginated` | 200 | Response has `count`, `next`, `previous`, `results` |
| `test_password_not_in_response` | 200/201 | `password` key absent from response body |

**Pass Criteria:** Full CRUD cycle completes; referential integrity enforced.

---

### `tests/test_ride_list.py` — Ride List Endpoint (Critical)

#### Filtering Tests

| Test Case | Query Params | Expected |
|---|---|---|
| `test_filter_by_status_en_route` | `?status=en-route` | Only `en-route` rides returned |
| `test_filter_by_status_pickup` | `?status=pickup` | Only `pickup` rides returned |
| `test_filter_by_status_dropoff` | `?status=dropoff` | Only `dropoff` rides returned |
| `test_filter_by_invalid_status` | `?status=cancelled` | HTTP 400 with `status` field error |
| `test_filter_by_rider_email_match` | `?rider_email=rider@test.com` | Returns rides for that rider |
| `test_filter_by_rider_email_no_match` | `?rider_email=unknown@test.com` | HTTP 200, empty `results` |
| `test_filter_by_invalid_email_format` | `?rider_email=notanemail` | HTTP 400 |
| `test_combined_status_and_email_filter` | `?status=en-route&rider_email=rider@test.com` | Intersection of both filters |

#### Sorting Tests

| Test Case | Query Params | Expected |
|---|---|---|
| `test_default_sort_is_pickup_time_asc` | No sort params | Results ordered by `pickup_time` ascending |
| `test_sort_by_pickup_time` | `?sort=pickup_time` | Ordered by `pickup_time` ascending |
| `test_sort_by_distance` | `?lat=37.77&lon=-122.41` | Nearest ride first |
| `test_distance_sort_precedence_over_time` | `?lat=37.77&lon=-122.41&sort=pickup_time` | Distance sort applied (takes precedence) |
| `test_distance_sort_missing_lon` | `?lat=37.77` | HTTP 400 — both required |
| `test_distance_sort_missing_lat` | `?lon=-122.41` | HTTP 400 — both required |
| `test_distance_sort_non_numeric_lat` | `?lat=abc&lon=-122.41` | HTTP 400 |
| `test_distance_sort_non_numeric_lon` | `?lat=37.77&lon=xyz` | HTTP 400 |
| `test_distance_sort_lat_out_of_range` | `?lat=91&lon=-122.41` | HTTP 400 |
| `test_distance_sort_lon_out_of_range` | `?lat=37.77&lon=200` | HTTP 400 |

#### Response Shape Tests

| Test Case | Expected |
|---|---|
| `test_ride_list_includes_id_rider_object` | `id_rider` is nested object with user fields |
| `test_ride_list_includes_id_driver_object` | `id_driver` is nested object with user fields |
| `test_ride_list_includes_todays_ride_events` | `todays_ride_events` field present |
| `test_ride_list_no_ride_events_field` | `ride_events` NOT present in list response |
| `test_todays_events_only_last_24h` | Events older than 24h excluded from `todays_ride_events` |
| `test_todays_events_empty_for_no_recent_events` | `todays_ride_events` is `[]` when no events in 24h |
| `test_ride_list_pagination_envelope` | Response has `count`, `next`, `previous`, `results` |
| `test_pagination_page_size` | `?page_size=5` returns max 5 results |
| `test_pagination_page_2` | `?page=2` returns second page |
| `test_pagination_with_distance_sort` | Page 2 with distance sort returns correct ordered subset |

```python
# tests/test_ride_list.py (sample)

@pytest.mark.django_db
def test_todays_events_only_last_24h(authenticated_client, sample_ride, todays_event, old_event):
    response = authenticated_client.get('/api/v1/rides/')
    assert response.status_code == 200
    ride_data = response.data['results'][0]
    event_ids = [e['id_ride_event'] for e in ride_data['todays_ride_events']]
    assert todays_event.id_ride_event in event_ids
    assert old_event.id_ride_event not in event_ids


@pytest.mark.django_db
def test_filter_by_invalid_status(authenticated_client):
    response = authenticated_client.get('/api/v1/rides/?status=cancelled')
    assert response.status_code == 400
    assert 'status' in response.data


@pytest.mark.django_db
def test_distance_sort_missing_lon(authenticated_client):
    response = authenticated_client.get('/api/v1/rides/?lat=37.77')
    assert response.status_code == 400
    assert 'error' in response.data or 'lon' in str(response.data).lower()


@pytest.mark.django_db
def test_distance_sort_ordering(authenticated_client, db, rider_user, driver_user):
    # Create two rides at different distances
    Ride.objects.create(
        status='en-route', id_rider=rider_user, id_driver=driver_user,
        pickup_latitude=37.77, pickup_longitude=-122.41,
        dropoff_latitude=37.33, dropoff_longitude=-121.88,
        pickup_time=timezone.now(),
    )
    Ride.objects.create(
        status='en-route', id_rider=rider_user, id_driver=driver_user,
        pickup_latitude=40.71, pickup_longitude=-74.00,  # NYC — far away
        dropoff_latitude=40.65, dropoff_longitude=-73.94,
        pickup_time=timezone.now(),
    )
    # Sort by distance from SF
    response = authenticated_client.get('/api/v1/rides/?lat=37.7749&lon=-122.4194')
    assert response.status_code == 200
    results = response.data['results']
    assert len(results) >= 2
    # First result should be the SF ride (closer)
    assert abs(results[0]['pickup_latitude'] - 37.77) < 0.1
```

**Pass Criteria:** All 35 Ride list tests pass; no regressions on CRUD.

---

### `tests/test_ride_crud.py` — Ride CRUD (Non-List)

| Test Case | Expected |
|---|---|
| `test_create_ride_valid` | 201, `id_ride` in response |
| `test_create_ride_invalid_status` | 400, `status` field error |
| `test_create_ride_nonexistent_rider` | 400, FK field error |
| `test_create_ride_nonexistent_driver` | 400, FK field error |
| `test_create_ride_latitude_invalid` | 400, coordinate field error |
| `test_retrieve_ride_includes_full_events` | 200, `ride_events` (all-time) present |
| `test_retrieve_ride_no_todays_events_field` | 200, `todays_ride_events` NOT in detail response |
| `test_retrieve_nonexistent_ride` | 404 |
| `test_update_ride_status` | 200, `status` updated |
| `test_partial_update_ride` | 200, only specified field changed |
| `test_delete_ride` | 204, ride and its events deleted |
| `test_delete_ride_cascades_events` | After delete, associated `RideEvent` records gone |

**Pass Criteria:** Full CRUD cycle passes; cascade delete verified.

---

### `tests/test_ride_event_endpoints.py` — RideEvent CRUD

| Test Case | Expected |
|---|---|
| `test_create_event_valid` | 201, linked to ride |
| `test_create_event_nonexistent_ride` | 400 |
| `test_list_events_all` | 200, paginated |
| `test_list_events_filter_by_ride` | `?ride=1` returns only events for ride 1 |
| `test_retrieve_event` | 200, correct object |
| `test_update_event` | 200, description updated |
| `test_delete_event` | 204 |
| `test_retrieve_nonexistent_event` | 404 |

**Pass Criteria:** Full CRUD cycle for RideEvent passes; filter by ride works.

---

## Query Count Tests (Performance Critical)

**This is the most important test category.** These tests directly validate FR-025 and NFR-001.

```python
# tests/test_query_count.py

import pytest
from django.test.utils import override_settings
from django.db import connection, reset_queries
from django.utils import timezone
from datetime import timedelta
from rides.models import User, Ride, RideEvent


def get_query_count_for_request(client, url):
    """Helper: make request and return number of SQL queries executed."""
    reset_queries()
    response = client.get(url)
    return len(connection.queries), response


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ride_list_max_3_queries_no_filters(authenticated_client, db, rider_user, driver_user):
    """
    Ride list with no filters should execute at most 3 queries:
    1. COUNT for pagination
    2. SELECT rides + JOINed users
    3. SELECT prefetched todays_ride_events
    """
    # Create 10 rides with events
    for i in range(10):
        ride = Ride.objects.create(
            status='en-route', id_rider=rider_user, id_driver=driver_user,
            pickup_latitude=37.77 + i * 0.01, pickup_longitude=-122.41,
            dropoff_latitude=37.33, dropoff_longitude=-121.88,
            pickup_time=timezone.now() - timedelta(hours=i),
        )
        RideEvent.objects.create(
            id_ride=ride,
            description=f'Event {i}',
            created_at=timezone.now() - timedelta(minutes=i * 10),
        )

    count, response = get_query_count_for_request(
        authenticated_client, '/api/v1/rides/'
    )

    assert response.status_code == 200
    assert count <= 3, (
        f"Expected max 3 queries, got {count}. "
        f"Queries: {[q['sql'] for q in connection.queries]}"
    )


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ride_list_max_3_queries_with_status_filter(authenticated_client, db, rider_user, driver_user):
    """Query count must not exceed 3 even when status filter is applied."""
    for i in range(5):
        Ride.objects.create(
            status='en-route', id_rider=rider_user, id_driver=driver_user,
            pickup_latitude=37.77, pickup_longitude=-122.41,
            dropoff_latitude=37.33, dropoff_longitude=-121.88,
            pickup_time=timezone.now(),
        )

    count, response = get_query_count_for_request(
        authenticated_client, '/api/v1/rides/?status=en-route'
    )

    assert response.status_code == 200
    assert count <= 3, f"Expected max 3 queries, got {count}"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ride_list_max_3_queries_with_distance_sort(authenticated_client, db, rider_user, driver_user):
    """Query count must not exceed 3 when distance sort annotation is applied."""
    for i in range(5):
        Ride.objects.create(
            status='en-route', id_rider=rider_user, id_driver=driver_user,
            pickup_latitude=37.77 + i * 0.01, pickup_longitude=-122.41 + i * 0.01,
            dropoff_latitude=37.33, dropoff_longitude=-121.88,
            pickup_time=timezone.now(),
        )

    count, response = get_query_count_for_request(
        authenticated_client, '/api/v1/rides/?lat=37.7749&lon=-122.4194'
    )

    assert response.status_code == 200
    assert count <= 3, f"Expected max 3 queries, got {count}"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_todays_ride_events_sql_has_date_filter(authenticated_client, db, rider_user, driver_user):
    """
    Verify that the SQL for todays_ride_events includes a date predicate
    (NOT a full table scan followed by Python filtering).
    """
    ride = Ride.objects.create(
        status='en-route', id_rider=rider_user, id_driver=driver_user,
        pickup_latitude=37.77, pickup_longitude=-122.41,
        dropoff_latitude=37.33, dropoff_longitude=-121.88,
        pickup_time=timezone.now(),
    )
    RideEvent.objects.create(
        id_ride=ride, description='Old event',
        created_at=timezone.now() - timedelta(hours=48)
    )
    RideEvent.objects.create(
        id_ride=ride, description='Recent event',
        created_at=timezone.now() - timedelta(hours=1)
    )

    reset_queries()
    response = authenticated_client.get('/api/v1/rides/')
    queries = connection.queries

    # Find the RideEvent query
    event_queries = [q['sql'] for q in queries if 'rideevent' in q['sql'].lower()]
    assert len(event_queries) >= 1, "Expected at least one RideEvent query"

    # The query must contain a date comparison
    event_query_sql = event_queries[0]
    assert 'created_at' in event_query_sql.lower(), (
        f"Expected created_at filter in RideEvent query. Got: {event_query_sql}"
    )

    # Verify only 1 recent event in response (not 2)
    results = response.data['results']
    assert len(results) == 1
    assert len(results[0]['todays_ride_events']) == 1
    assert results[0]['todays_ride_events'][0]['description'] == 'Recent event'


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_no_n_plus_1_queries_on_large_page(authenticated_client, db, rider_user, driver_user):
    """
    Query count must remain <= 3 regardless of page size.
    Verifies absence of N+1 pattern — queries should NOT scale with result count.
    """
    # Create 50 rides
    for i in range(50):
        Ride.objects.create(
            status='en-route', id_rider=rider_user, id_driver=driver_user,
            pickup_latitude=37.77 + i * 0.001, pickup_longitude=-122.41,
            dropoff_latitude=37.33, dropoff_longitude=-121.88,
            pickup_time=timezone.now() - timedelta(minutes=i),
        )

    count_10, _ = get_query_count_for_request(
        authenticated_client, '/api/v1/rides/?page_size=10'
    )
    count_50, _ = get_query_count_for_request(
        authenticated_client, '/api/v1/rides/?page_size=50'
    )

    assert count_10 <= 3
    assert count_50 <= 3
    # Most importantly: query count doesn't grow with page size
    assert count_50 <= count_10 + 1, (
        f"Query count grew with page size: 10 items={count_10}, 50 items={count_50}. "
        "N+1 pattern detected."
    )
```

**Pass Criteria (NFR-001, FR-025):**
- All four query count tests pass.
- No test shows > 3 queries for the Ride list endpoint.
- The `todays_ride_events` SQL contains a `created_at` filter.

---

## Security Tests

### `tests/test_security.py`

| Test Case | Input | Expected |
|---|---|---|
| `test_all_endpoints_require_auth` | No `Authorization` header on each of 18 CRUD endpoints | All return 401 |
| `test_non_admin_role_all_endpoints` | Rider token on each endpoint | All return 403 |
| `test_error_body_is_json` | Invalid request (unauthenticated) | `Content-Type: application/json` |
| `test_password_not_in_user_list_response` | `GET /api/v1/users/` | `password` absent from all user objects in `results` |
| `test_password_not_in_create_response` | `POST /api/v1/users/` with password | `password` absent from 201 response |
| `test_password_not_in_retrieve_response` | `GET /api/v1/users/1/` | `password` absent |
| `test_sql_injection_status_param` | `?status=en-route'; DROP TABLE rides_ride; --` | HTTP 400, no DB error |
| `test_sql_injection_rider_email` | `?rider_email=' OR 1=1 --` | HTTP 400 (invalid email format) |
| `test_coordinate_boundary_min_lat` | `pickup_latitude=-90` | Accepted (valid) |
| `test_coordinate_boundary_max_lat` | `pickup_latitude=90` | Accepted (valid) |
| `test_coordinate_beyond_max_lat` | `pickup_latitude=90.001` | HTTP 400 |
| `test_coordinate_beyond_min_lon` | `pickup_longitude=-180.001` | HTTP 400 |

```python
# tests/test_security.py (sample)

@pytest.mark.django_db
@pytest.mark.parametrize('method,url', [
    ('get',    '/api/v1/users/'),
    ('post',   '/api/v1/users/'),
    ('get',    '/api/v1/users/1/'),
    ('put',    '/api/v1/users/1/'),
    ('patch',  '/api/v1/users/1/'),
    ('delete', '/api/v1/users/1/'),
    ('get',    '/api/v1/rides/'),
    ('post',   '/api/v1/rides/'),
    ('get',    '/api/v1/rides/1/'),
    ('put',    '/api/v1/rides/1/'),
    ('patch',  '/api/v1/rides/1/'),
    ('delete', '/api/v1/rides/1/'),
    ('get',    '/api/v1/events/'),
    ('post',   '/api/v1/events/'),
    ('get',    '/api/v1/events/1/'),
    ('put',    '/api/v1/events/1/'),
    ('patch',  '/api/v1/events/1/'),
    ('delete', '/api/v1/events/1/'),
])
def test_all_endpoints_require_auth(api_client, method, url):
    response = getattr(api_client, method)(url)
    assert response.status_code == 401
    assert 'application/json' in response['Content-Type']


@pytest.mark.django_db
def test_password_not_in_response(authenticated_client, admin_user):
    response = authenticated_client.get(f'/api/v1/users/{admin_user.id_user}/')
    assert response.status_code == 200
    assert 'password' not in response.data
```

**Pass Criteria:** All security tests pass; no endpoint bypasses auth; password never exposed.

---

## End-to-End Tests

### E2E Workflow 1: Admin Creates and Manages a Ride

```
1. POST /api/v1/auth/token/           → obtain admin token
2. POST /api/v1/users/ (rider)        → create rider user
3. POST /api/v1/users/ (driver)       → create driver user
4. POST /api/v1/rides/                → create ride with rider/driver
5. POST /api/v1/events/               → create en-route event for ride
6. GET  /api/v1/rides/                → list contains ride; todays_ride_events has 1 event
7. PATCH /api/v1/rides/{id}/          → update status to 'pickup'
8. POST /api/v1/events/               → create pickup event
9. GET  /api/v1/rides/{id}/           → detail shows all 2 events in ride_events
10. PATCH /api/v1/rides/{id}/         → update status to 'dropoff'
11. POST /api/v1/events/              → create dropoff event
12. DELETE /api/v1/rides/{id}/        → delete ride
13. GET /api/v1/rides/{id}/           → 404 confirmed; events also deleted
```

**Pass Criteria:** All 13 steps return expected HTTP codes and data shapes.

---

### E2E Workflow 2: Admin Filters and Paginates Ride List

```
1. Create 25 rides: 10 'en-route', 10 'pickup', 5 'dropoff'
2. GET /api/v1/rides/?status=en-route&page_size=5 → 10 total, 5 on page 1
3. GET /api/v1/rides/?status=en-route&page=2 → next 5 en-route rides
4. GET /api/v1/rides/?rider_email=<rider email> → all rides for that rider
5. GET /api/v1/rides/?lat=37.77&lon=-122.41&page_size=3 → 3 nearest rides
6. GET /api/v1/rides/?lat=37.77&lon=-122.41&page=2 → next 3 nearest rides (correct offset)
```

**Pass Criteria:** Pagination counts are stable; sort order is consistent across pages.

---

## Acceptance Criteria Summary

| Criterion | Test File | Pass Condition |
|---|---|---|
| 401 for unauthenticated | `test_security.py` | 18 endpoints all return 401 |
| 403 for non-admin | `test_security.py` | 18 endpoints all return 403 |
| Max 3 queries for Ride list | `test_query_count.py` | All 4 query count assertions pass |
| `todays_ride_events` SQL-filtered | `test_query_count.py` | SQL contains `created_at` predicate |
| No N+1 queries | `test_query_count.py` | Query count flat regardless of page size |
| `password` never in response | `test_security.py` | `password` key absent from all responses |
| HTTP 400 for invalid `status` | `test_ride_list.py` | Returns 400 with field error |
| HTTP 400 for non-numeric lat/lon | `test_ride_list.py` | Returns 400 with descriptive error |
| HTTP 400 for missing lat or lon | `test_ride_list.py` | Returns 400 |
| Distance sort nearest-first | `test_ride_list.py` | Closest ride is first result |
| User DELETE with rides → 409 | `test_user_endpoints.py` | Returns 409, not 500 |
| Ride DELETE cascades events | `test_ride_crud.py` | Events gone after ride deleted |
| Coordinate range validation | `test_serializers.py` + `test_security.py` | Out-of-range coords return 400 |
| All errors return JSON | `test_security.py` | `Content-Type: application/json` on all errors |
| Full User CRUD | `test_user_endpoints.py` | All operations succeed |
| Full Ride CRUD | `test_ride_crud.py` | All operations succeed |
| Full RideEvent CRUD | `test_ride_event_endpoints.py` | All operations succeed |

---

## Test Coverage Goals

| Module | Target Coverage |
|---|---|
| `rides/permissions.py` | 100% |
| `rides/serializers.py` | 90%+ |
| `rides/views.py` | 85%+ |
| `rides/models.py` | 70%+ (model logic is minimal) |
| `rides/pagination.py` | 80%+ |
| **Overall project** | **85%+** |

**Coverage command:**
```bash
pytest tests/ --cov=rides --cov-report=term-missing
```

---

## Known Gaps

| Gap | Justification |
|---|---|
| Load testing (k6, JMeter) | Out of scope per BRD. Query count tests serve as the performance gate. |
| Token expiry / rotation tests | DRF Token Auth has no built-in expiry; no expiry logic is implemented. |
| Multi-tenant isolation tests | BRD explicitly states no multi-tenancy. |
| HTTPS / TLS tests | Infrastructure concern; out of scope. |
| Concurrent write tests | Assessment is single-user operational tool; concurrency not in BRD. |
| SQLite trig function failure tests | Dev-only concern; PostgreSQL used in production. Dev fallback approximation is an implementation note, not a testable behavior. |
| Bonus SQL query execution test | The SQL is PostgreSQL-dialect. Running it requires a PostgreSQL DB; test environment uses SQLite. A separate manual verification step against PostgreSQL is recommended. |
