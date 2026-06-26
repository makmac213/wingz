"""Token endpoint + core auth gating (named per the implementation prompt)."""

import pytest


@pytest.mark.django_db
def test_obtain_token_with_valid_credentials(api_client, admin_user):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"username": admin_user.email, "password": "admin123"},
        format="json",
    )
    assert response.status_code == 200
    assert "token" in response.data
    assert len(response.data["token"]) > 0


@pytest.mark.django_db
def test_obtain_token_with_invalid_credentials(api_client, admin_user):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"username": admin_user.email, "password": "wrong"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_unauthenticated_request_returns_401(api_client):
    response = api_client.get("/api/v1/rides/")
    assert response.status_code == 401
    assert "application/json" in response["Content-Type"]


@pytest.mark.django_db
def test_non_admin_request_returns_403(api_client, rider_user):
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=rider_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    response = api_client.get("/api/v1/rides/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_request_returns_200(authenticated_client):
    assert authenticated_client.get("/api/v1/rides/").status_code == 200
