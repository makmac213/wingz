"""IsAdminRole unit tests + API auth/permission enforcement tests."""

from unittest.mock import MagicMock

import pytest
from rest_framework.authtoken.models import Token

from rides.permissions import IsAdminRole


def _make_request(user):
    request = MagicMock()
    request.user = user
    return request


# --------------------------------------------------------------------------
# Unit tests for the permission class
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "role,expected",
    [
        ("admin", True),
        ("rider", False),
        (None, False),
        ("", False),
    ],
)
def test_admin_role_permission(role, expected):
    permission = IsAdminRole()
    user = MagicMock()
    user.is_authenticated = True
    user.role = role
    assert permission.has_permission(_make_request(user), None) is expected


def test_unauthenticated_user_denied():
    permission = IsAdminRole()
    user = MagicMock()
    user.is_authenticated = False
    assert permission.has_permission(_make_request(user), None) is False


def test_none_user_denied():
    permission = IsAdminRole()
    request = MagicMock()
    request.user = None
    assert permission.has_permission(request, None) is False


# --------------------------------------------------------------------------
# Integration: API auth enforcement
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_list_users_unauthenticated(api_client):
    response = api_client.get("/api/v1/users/")
    assert response.status_code == 401
    assert "application/json" in response["Content-Type"]


@pytest.mark.django_db
def test_list_users_non_admin(api_client, rider_user):
    token, _ = Token.objects.get_or_create(user=rider_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = api_client.get("/api/v1/users/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_users_admin(authenticated_client):
    response = authenticated_client.get("/api/v1/users/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_list_rides_unauthenticated(api_client):
    assert api_client.get("/api/v1/rides/").status_code == 401


@pytest.mark.django_db
def test_list_events_unauthenticated(api_client):
    assert api_client.get("/api/v1/events/").status_code == 401


@pytest.mark.django_db
def test_create_user_unauthenticated(api_client):
    assert api_client.post("/api/v1/users/", {}, format="json").status_code == 401


@pytest.mark.django_db
def test_delete_ride_non_admin(api_client, rider_user, sample_ride):
    token, _ = Token.objects.get_or_create(user=rider_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = api_client.delete(f"/api/v1/rides/{sample_ride.id_ride}/")
    assert response.status_code == 403
