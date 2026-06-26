"""Security tests: auth gating across all endpoints, password protection,
injection resistance, coordinate boundaries.
"""

import pytest
from rest_framework.authtoken.models import Token

ALL_ENDPOINTS = [
    ("get", "/api/v1/users/"),
    ("post", "/api/v1/users/"),
    ("get", "/api/v1/users/1/"),
    ("put", "/api/v1/users/1/"),
    ("patch", "/api/v1/users/1/"),
    ("delete", "/api/v1/users/1/"),
    ("get", "/api/v1/rides/"),
    ("post", "/api/v1/rides/"),
    ("get", "/api/v1/rides/1/"),
    ("put", "/api/v1/rides/1/"),
    ("patch", "/api/v1/rides/1/"),
    ("delete", "/api/v1/rides/1/"),
    ("get", "/api/v1/events/"),
    ("post", "/api/v1/events/"),
    ("get", "/api/v1/events/1/"),
    ("put", "/api/v1/events/1/"),
    ("patch", "/api/v1/events/1/"),
    ("delete", "/api/v1/events/1/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method,url", ALL_ENDPOINTS)
def test_all_endpoints_require_auth(api_client, method, url):
    response = getattr(api_client, method)(url)
    assert response.status_code == 401
    assert "application/json" in response["Content-Type"]


@pytest.mark.django_db
@pytest.mark.parametrize("method,url", ALL_ENDPOINTS)
def test_all_endpoints_reject_non_admin(api_client, rider_user, method, url):
    token, _ = Token.objects.get_or_create(user=rider_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = getattr(api_client, method)(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_password_not_in_retrieve(authenticated_client, admin_user):
    response = authenticated_client.get(f"/api/v1/users/{admin_user.id_user}/")
    assert response.status_code == 200
    assert "password" not in response.data


@pytest.mark.django_db
def test_password_not_in_create_response(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/users/",
        {
            "role": "rider",
            "first_name": "P",
            "last_name": "W",
            "email": "pw@test.com",
            "phone_number": "+1",
            "password": "secret123",
        },
        format="json",
    )
    assert response.status_code == 201
    assert "password" not in response.data


@pytest.mark.django_db
def test_sql_injection_status_param(authenticated_client):
    response = authenticated_client.get(
        "/api/v1/rides/?status=en-route'; DROP TABLE rides_ride; --"
    )
    # Invalid status -> 400, no DB error / no table dropped.
    assert response.status_code == 400


@pytest.mark.django_db
def test_sql_injection_rider_email(authenticated_client):
    response = authenticated_client.get(
        "/api/v1/rides/?rider_email=' OR 1=1 --"
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lat,valid",
    [(-90, True), (90, True), (90.001, False)],
)
def test_coordinate_boundaries(
    authenticated_client, rider_user, driver_user, lat, valid
):
    payload = {
        "status": "en-route",
        "id_rider_id": rider_user.id_user,
        "id_driver_id": driver_user.id_user,
        "pickup_latitude": lat,
        "pickup_longitude": 0.0,
        "dropoff_latitude": 0.0,
        "dropoff_longitude": 0.0,
        "pickup_time": "2026-06-26T00:00:00Z",
    }
    response = authenticated_client.post(
        "/api/v1/rides/", payload, format="json"
    )
    assert response.status_code == (201 if valid else 400)
