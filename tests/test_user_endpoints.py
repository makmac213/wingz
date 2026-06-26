"""User CRUD endpoint tests."""

import pytest


@pytest.mark.django_db
def test_create_user_valid(authenticated_client):
    payload = {
        "role": "rider",
        "first_name": "New",
        "last_name": "Rider",
        "email": "new@test.com",
        "phone_number": "+19998887777",
        "password": "secret123",
    }
    response = authenticated_client.post(
        "/api/v1/users/", payload, format="json"
    )
    assert response.status_code == 201
    assert "id_user" in response.data
    assert "password" not in response.data


@pytest.mark.django_db
def test_create_user_duplicate_email(authenticated_client, rider_user):
    payload = {
        "role": "rider",
        "first_name": "Dup",
        "last_name": "Email",
        "email": rider_user.email,
        "phone_number": "+19998887777",
    }
    response = authenticated_client.post(
        "/api/v1/users/", payload, format="json"
    )
    assert response.status_code == 400
    assert "email" in response.data


@pytest.mark.django_db
def test_create_user_invalid_role(authenticated_client):
    payload = {
        "role": "superuser",
        "first_name": "Bad",
        "last_name": "Role",
        "email": "badrole@test.com",
        "phone_number": "+19998887777",
    }
    response = authenticated_client.post(
        "/api/v1/users/", payload, format="json"
    )
    assert response.status_code == 400
    assert "role" in response.data


@pytest.mark.django_db
def test_retrieve_user(authenticated_client, rider_user):
    response = authenticated_client.get(f"/api/v1/users/{rider_user.id_user}/")
    assert response.status_code == 200
    assert response.data["email"] == rider_user.email
    assert "password" not in response.data


@pytest.mark.django_db
def test_retrieve_nonexistent_user(authenticated_client):
    response = authenticated_client.get("/api/v1/users/999999/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_partial_update_user(authenticated_client, rider_user):
    response = authenticated_client.patch(
        f"/api/v1/users/{rider_user.id_user}/",
        {"first_name": "Renamed"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["first_name"] == "Renamed"


@pytest.mark.django_db
def test_delete_user_no_rides(authenticated_client, rider_user):
    response = authenticated_client.delete(
        f"/api/v1/users/{rider_user.id_user}/"
    )
    assert response.status_code == 204


@pytest.mark.django_db
def test_delete_user_with_rides_returns_409(
    authenticated_client, sample_ride
):
    rider_id = sample_ride.id_rider.id_user
    response = authenticated_client.delete(f"/api/v1/users/{rider_id}/")
    assert response.status_code == 409
    assert "error" in response.data


@pytest.mark.django_db
def test_list_users_paginated(authenticated_client, admin_user):
    response = authenticated_client.get("/api/v1/users/")
    assert response.status_code == 200
    for key in ("count", "next", "previous", "results"):
        assert key in response.data
    assert all("password" not in u for u in response.data["results"])
