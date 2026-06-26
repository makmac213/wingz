"""Query-count assertions for the Ride list endpoint (NFR-001, FR-025).

These tests measure the *endpoint* query budget: COUNT + data(JOINs) + prefetch
= 3 queries max, regardless of page size. They use ``query_count_client``
(force-authenticated) so the per-request token-auth lookup is excluded from the
measured window; auth itself is verified in test_permissions.py.
"""

from datetime import timedelta

import pytest
from django.db import connection, reset_queries
from django.test.utils import override_settings
from django.utils import timezone

from rides.models import Ride, RideEvent

MAX_QUERIES = 3


def _request_query_count(client, url):
    reset_queries()
    response = client.get(url)
    return len(connection.queries), response


def _seed_rides(rider, driver, n, with_events=True):
    now = timezone.now()
    for i in range(n):
        ride = Ride.objects.create(
            status="en-route",
            id_rider=rider,
            id_driver=driver,
            pickup_latitude=37.77 + i * 0.001,
            pickup_longitude=-122.41,
            dropoff_latitude=37.33,
            dropoff_longitude=-121.88,
            pickup_time=now - timedelta(minutes=i),
        )
        if with_events:
            RideEvent.objects.create(
                id_ride=ride,
                description=f"Event {i}",
                created_at=now - timedelta(minutes=i),
            )


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ride_list_max_queries_no_filters(
    query_count_client, rider_user, driver_user
):
    _seed_rides(rider_user, driver_user, 10)
    count, response = _request_query_count(query_count_client, "/api/v1/rides/")
    assert response.status_code == 200
    assert count <= MAX_QUERIES, (
        f"Expected <= {MAX_QUERIES} queries, got {count}: "
        f"{[q['sql'] for q in connection.queries]}"
    )


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ride_list_max_queries_with_status_filter(
    query_count_client, rider_user, driver_user
):
    _seed_rides(rider_user, driver_user, 5)
    count, response = _request_query_count(
        query_count_client, "/api/v1/rides/?status=en-route"
    )
    assert response.status_code == 200
    assert count <= MAX_QUERIES, f"Expected <= {MAX_QUERIES}, got {count}"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ride_list_max_queries_with_distance_sort(
    query_count_client, rider_user, driver_user
):
    _seed_rides(rider_user, driver_user, 5)
    count, response = _request_query_count(
        query_count_client, "/api/v1/rides/?lat=37.7749&lon=-122.4194"
    )
    assert response.status_code == 200
    assert count <= MAX_QUERIES, f"Expected <= {MAX_QUERIES}, got {count}"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_todays_events_sql_has_date_filter(
    query_count_client, rider_user, driver_user
):
    now = timezone.now()
    ride = Ride.objects.create(
        status="en-route",
        id_rider=rider_user,
        id_driver=driver_user,
        pickup_latitude=37.77,
        pickup_longitude=-122.41,
        dropoff_latitude=37.33,
        dropoff_longitude=-121.88,
        pickup_time=now,
    )
    RideEvent.objects.create(
        id_ride=ride, description="Old event",
        created_at=now - timedelta(hours=48),
    )
    RideEvent.objects.create(
        id_ride=ride, description="Recent event",
        created_at=now - timedelta(hours=1),
    )

    reset_queries()
    response = query_count_client.get("/api/v1/rides/")
    event_queries = [
        q["sql"] for q in connection.queries
        if "rideevent" in q["sql"].lower()
    ]
    assert event_queries, "Expected at least one RideEvent query"
    assert "created_at" in event_queries[0].lower()

    results = response.data["results"]
    assert len(results) == 1
    assert len(results[0]["todays_ride_events"]) == 1
    assert results[0]["todays_ride_events"][0]["description"] == "Recent event"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_no_n_plus_1_on_large_page(
    query_count_client, rider_user, driver_user
):
    _seed_rides(rider_user, driver_user, 50)
    count_10, _ = _request_query_count(
        query_count_client, "/api/v1/rides/?page_size=10"
    )
    count_50, _ = _request_query_count(
        query_count_client, "/api/v1/rides/?page_size=50"
    )
    assert count_10 <= MAX_QUERIES
    assert count_50 <= MAX_QUERIES
    assert count_50 <= count_10 + 1, (
        f"Query count grew with page size (10={count_10}, 50={count_50}); "
        "N+1 pattern detected."
    )
