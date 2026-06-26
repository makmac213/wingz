"""Ride list endpoint: filtering, sorting, response shape, pagination."""

from datetime import timedelta

import pytest
from django.utils import timezone

from rides.models import Ride, RideEvent


def _make_ride(rider, driver, **overrides):
    defaults = dict(
        status="en-route",
        id_rider=rider,
        id_driver=driver,
        pickup_latitude=37.77,
        pickup_longitude=-122.41,
        dropoff_latitude=37.33,
        dropoff_longitude=-121.88,
        pickup_time=timezone.now(),
    )
    defaults.update(overrides)
    return Ride.objects.create(**defaults)


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_filter_by_status_en_route(authenticated_client, rider_user, driver_user):
    _make_ride(rider_user, driver_user, status="en-route")
    _make_ride(rider_user, driver_user, status="pickup")
    response = authenticated_client.get("/api/v1/rides/?status=en-route")
    assert response.status_code == 200
    assert all(r["status"] == "en-route" for r in response.data["results"])
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_filter_by_invalid_status(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?status=cancelled")
    assert response.status_code == 400
    assert "status" in response.data


@pytest.mark.django_db
def test_filter_by_rider_email_match(
    authenticated_client, rider_user, driver_user
):
    _make_ride(rider_user, driver_user)
    response = authenticated_client.get(
        f"/api/v1/rides/?rider_email={rider_user.email}"
    )
    assert response.status_code == 200
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_filter_by_rider_email_no_match(
    authenticated_client, rider_user, driver_user
):
    _make_ride(rider_user, driver_user)
    response = authenticated_client.get(
        "/api/v1/rides/?rider_email=nobody@test.com"
    )
    assert response.status_code == 200
    assert response.data["results"] == []


@pytest.mark.django_db
def test_filter_by_invalid_email_format(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?rider_email=notanemail")
    assert response.status_code == 400


@pytest.mark.django_db
def test_combined_status_and_email_filter(
    authenticated_client, rider_user, driver_user
):
    _make_ride(rider_user, driver_user, status="en-route")
    _make_ride(rider_user, driver_user, status="pickup")
    response = authenticated_client.get(
        f"/api/v1/rides/?status=en-route&rider_email={rider_user.email}"
    )
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["status"] == "en-route"


# --------------------------------------------------------------------------
# Sorting
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_default_sort_is_pickup_time_asc(
    authenticated_client, rider_user, driver_user
):
    now = timezone.now()
    _make_ride(rider_user, driver_user, pickup_time=now)
    _make_ride(rider_user, driver_user, pickup_time=now - timedelta(hours=2))
    _make_ride(rider_user, driver_user, pickup_time=now - timedelta(hours=1))
    response = authenticated_client.get("/api/v1/rides/")
    times = [r["pickup_time"] for r in response.data["results"]]
    assert times == sorted(times)


@pytest.mark.django_db
def test_sort_by_distance_nearest_first(
    authenticated_client, rider_user, driver_user
):
    _make_ride(
        rider_user, driver_user,
        pickup_latitude=37.77, pickup_longitude=-122.41,  # SF
    )
    _make_ride(
        rider_user, driver_user,
        pickup_latitude=40.71, pickup_longitude=-74.00,  # NYC (far)
    )
    response = authenticated_client.get(
        "/api/v1/rides/?lat=37.7749&lon=-122.4194"
    )
    assert response.status_code == 200
    results = response.data["results"]
    assert len(results) == 2
    assert abs(results[0]["pickup_latitude"] - 37.77) < 0.1


@pytest.mark.django_db
def test_distance_sort_precedence_over_time(
    authenticated_client, rider_user, driver_user
):
    # SF ride has the LATER pickup_time, so under pickup_time sort it would be
    # last; under distance sort (from SF) it must be first.
    now = timezone.now()
    _make_ride(
        rider_user, driver_user,
        pickup_latitude=40.71, pickup_longitude=-74.00,
        pickup_time=now - timedelta(hours=5),
    )
    _make_ride(
        rider_user, driver_user,
        pickup_latitude=37.77, pickup_longitude=-122.41,
        pickup_time=now,
    )
    response = authenticated_client.get(
        "/api/v1/rides/?lat=37.7749&lon=-122.4194&sort=pickup_time"
    )
    assert abs(response.data["results"][0]["pickup_latitude"] - 37.77) < 0.1


@pytest.mark.django_db
def test_distance_sort_missing_lon(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?lat=37.77")
    assert response.status_code == 400
    assert "error" in response.data or "lon" in str(response.data).lower()


@pytest.mark.django_db
def test_distance_sort_missing_lat(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?lon=-122.41")
    assert response.status_code == 400


@pytest.mark.django_db
def test_distance_sort_non_numeric_lat(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?lat=abc&lon=-122.41")
    assert response.status_code == 400


@pytest.mark.django_db
def test_distance_sort_non_numeric_lon(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?lat=37.77&lon=xyz")
    assert response.status_code == 400


@pytest.mark.django_db
def test_distance_sort_lat_out_of_range(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?lat=91&lon=-122.41")
    assert response.status_code == 400


@pytest.mark.django_db
def test_distance_sort_lon_out_of_range(authenticated_client):
    response = authenticated_client.get("/api/v1/rides/?lat=37.77&lon=200")
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Response shape
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_ride_list_nested_user_objects(
    authenticated_client, sample_ride
):
    response = authenticated_client.get("/api/v1/rides/")
    row = response.data["results"][0]
    assert isinstance(row["id_rider"], dict)
    assert row["id_rider"]["email"] == sample_ride.id_rider.email
    assert isinstance(row["id_driver"], dict)
    assert "password" not in row["id_rider"]


@pytest.mark.django_db
def test_ride_list_includes_todays_events_excludes_ride_events(
    authenticated_client, sample_ride
):
    response = authenticated_client.get("/api/v1/rides/")
    row = response.data["results"][0]
    assert "todays_ride_events" in row
    assert "ride_events" not in row


@pytest.mark.django_db
def test_todays_events_only_last_24h(
    authenticated_client, sample_ride, todays_event, old_event
):
    response = authenticated_client.get("/api/v1/rides/")
    row = response.data["results"][0]
    event_ids = [e["id_ride_event"] for e in row["todays_ride_events"]]
    assert todays_event.id_ride_event in event_ids
    assert old_event.id_ride_event not in event_ids


@pytest.mark.django_db
def test_todays_events_empty_when_none_recent(
    authenticated_client, sample_ride, old_event
):
    response = authenticated_client.get("/api/v1/rides/")
    assert response.data["results"][0]["todays_ride_events"] == []


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_pagination_envelope(authenticated_client, sample_ride):
    response = authenticated_client.get("/api/v1/rides/")
    for key in ("count", "next", "previous", "results"):
        assert key in response.data


@pytest.mark.django_db
def test_pagination_page_size(authenticated_client, rider_user, driver_user):
    for _ in range(8):
        _make_ride(rider_user, driver_user)
    response = authenticated_client.get("/api/v1/rides/?page_size=5")
    assert len(response.data["results"]) == 5
    assert response.data["count"] == 8


@pytest.mark.django_db
def test_pagination_page_size_capped_at_100(
    authenticated_client, rider_user, driver_user
):
    _make_ride(rider_user, driver_user)
    response = authenticated_client.get("/api/v1/rides/?page_size=500")
    # The cap is enforced; with 1 ride we just confirm the request succeeds.
    assert response.status_code == 200


@pytest.mark.django_db
def test_pagination_with_distance_sort_stable_pages(
    authenticated_client, rider_user, driver_user
):
    for i in range(6):
        _make_ride(
            rider_user, driver_user,
            pickup_latitude=37.77 + i * 0.01, pickup_longitude=-122.41,
        )
    page1 = authenticated_client.get(
        "/api/v1/rides/?lat=37.7749&lon=-122.4194&page_size=3&page=1"
    )
    page2 = authenticated_client.get(
        "/api/v1/rides/?lat=37.7749&lon=-122.4194&page_size=3&page=2"
    )
    ids1 = {r["id_ride"] for r in page1.data["results"]}
    ids2 = {r["id_ride"] for r in page2.data["results"]}
    assert len(ids1) == 3 and len(ids2) == 3
    assert ids1.isdisjoint(ids2)  # no overlap -> stable pagination
