"""RideEvent CRUD endpoint tests."""

import pytest

from rides.models import Ride, RideEvent


@pytest.mark.django_db
def test_create_event_valid(authenticated_client, sample_ride):
    response = authenticated_client.post(
        "/api/v1/events/",
        {"id_ride": sample_ride.id_ride, "description": "Status changed"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["id_ride"] == sample_ride.id_ride


@pytest.mark.django_db
def test_create_event_nonexistent_ride(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/events/",
        {"id_ride": 999999, "description": "x"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_list_events_filter_by_ride(
    authenticated_client, sample_ride, rider_user, driver_user
):
    other_ride = Ride.objects.create(
        status="pickup", id_rider=rider_user, id_driver=driver_user,
        pickup_latitude=1, pickup_longitude=1,
        dropoff_latitude=2, dropoff_longitude=2,
        pickup_time="2026-01-01T00:00:00Z",
    )
    RideEvent.objects.create(id_ride=sample_ride, description="A")
    RideEvent.objects.create(id_ride=other_ride, description="B")

    response = authenticated_client.get(
        f"/api/v1/events/?ride={sample_ride.id_ride}"
    )
    assert response.status_code == 200
    assert all(
        e["id_ride"] == sample_ride.id_ride for e in response.data["results"]
    )
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_retrieve_update_delete_event(authenticated_client, sample_ride):
    event = RideEvent.objects.create(id_ride=sample_ride, description="orig")
    url = f"/api/v1/events/{event.id_ride_event}/"

    assert authenticated_client.get(url).status_code == 200

    patch = authenticated_client.patch(
        url, {"description": "updated"}, format="json"
    )
    assert patch.status_code == 200
    assert patch.data["description"] == "updated"

    assert authenticated_client.delete(url).status_code == 204
    assert not RideEvent.objects.filter(pk=event.pk).exists()


@pytest.mark.django_db
def test_retrieve_nonexistent_event(authenticated_client):
    assert authenticated_client.get("/api/v1/events/999999/").status_code == 404
