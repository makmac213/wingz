"""Ride CRUD (non-list) endpoint tests."""

import pytest
from django.utils import timezone

from rides.models import RideEvent


def _ride_payload(rider, driver, **overrides):
    payload = {
        "status": "en-route",
        "id_rider_id": rider.id_user,
        "id_driver_id": driver.id_user,
        "pickup_latitude": 37.77,
        "pickup_longitude": -122.41,
        "dropoff_latitude": 37.33,
        "dropoff_longitude": -121.88,
        "pickup_time": timezone.now().isoformat(),
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_ride_valid(authenticated_client, rider_user, driver_user):
    response = authenticated_client.post(
        "/api/v1/rides/",
        _ride_payload(rider_user, driver_user),
        format="json",
    )
    assert response.status_code == 201
    assert "id_ride" in response.data


@pytest.mark.django_db
def test_create_ride_invalid_status(
    authenticated_client, rider_user, driver_user
):
    response = authenticated_client.post(
        "/api/v1/rides/",
        _ride_payload(rider_user, driver_user, status="cancelled"),
        format="json",
    )
    assert response.status_code == 400
    assert "status" in response.data


@pytest.mark.django_db
def test_create_ride_nonexistent_rider(
    authenticated_client, driver_user
):
    payload = _ride_payload(driver_user, driver_user)
    payload["id_rider_id"] = 999999
    response = authenticated_client.post(
        "/api/v1/rides/", payload, format="json"
    )
    assert response.status_code == 400
    assert "id_rider_id" in response.data


@pytest.mark.django_db
def test_create_ride_latitude_out_of_range(
    authenticated_client, rider_user, driver_user
):
    response = authenticated_client.post(
        "/api/v1/rides/",
        _ride_payload(rider_user, driver_user, pickup_latitude=91.0),
        format="json",
    )
    assert response.status_code == 400
    assert "pickup_latitude" in response.data


@pytest.mark.django_db
def test_retrieve_ride_includes_full_events(
    authenticated_client, sample_ride, todays_event, old_event
):
    response = authenticated_client.get(f"/api/v1/rides/{sample_ride.id_ride}/")
    assert response.status_code == 200
    assert "ride_events" in response.data
    assert "todays_ride_events" not in response.data
    # Detail shows ALL events (both recent and old).
    assert len(response.data["ride_events"]) == 2


@pytest.mark.django_db
def test_retrieve_nonexistent_ride(authenticated_client):
    assert authenticated_client.get("/api/v1/rides/999999/").status_code == 404


@pytest.mark.django_db
def test_update_ride_status(authenticated_client, sample_ride):
    response = authenticated_client.patch(
        f"/api/v1/rides/{sample_ride.id_ride}/",
        {"status": "pickup"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "pickup"


@pytest.mark.django_db
def test_delete_ride_cascades_events(
    authenticated_client, sample_ride, todays_event
):
    ride_id = sample_ride.id_ride
    response = authenticated_client.delete(f"/api/v1/rides/{ride_id}/")
    assert response.status_code == 204
    assert not RideEvent.objects.filter(id_ride_id=ride_id).exists()
