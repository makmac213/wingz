"""Shared pytest fixtures."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from rides.models import Ride, RideEvent, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@test.com",
        password="admin123",
        role="admin",
        first_name="Admin",
        last_name="User",
        phone_number="+10000000001",
    )


@pytest.fixture
def rider_user(db):
    return User.objects.create_user(
        email="rider@test.com",
        password="rider123",
        role="rider",
        first_name="Rider",
        last_name="One",
        phone_number="+10000000002",
    )


@pytest.fixture
def driver_user(db):
    return User.objects.create_user(
        email="driver@test.com",
        password="driver123",
        role="rider",
        first_name="Driver",
        last_name="One",
        phone_number="+10000000003",
    )


@pytest.fixture
def admin_token(admin_user):
    token, _ = Token.objects.get_or_create(user=admin_user)
    return token.key


@pytest.fixture
def authenticated_client(api_client, admin_token):
    """Admin client authenticated via a real DRF token (exercises auth)."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token}")
    return api_client


@pytest.fixture
def query_count_client(api_client, admin_user):
    """Admin client authenticated WITHOUT a per-request token DB lookup.

    Token authentication adds one DB query per request to resolve the token ->
    user. The query-count tests measure the *endpoint's* query budget (COUNT +
    data + prefetch), so we use ``force_authenticate`` to remove auth overhead
    from the measured window. Auth itself is verified separately in
    ``test_permissions.py``.
    """
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def sample_ride(db, rider_user, driver_user):
    return Ride.objects.create(
        status="en-route",
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
        description="Status changed to en-route",
        created_at=timezone.now() - timedelta(hours=1),
    )


@pytest.fixture
def old_event(db, sample_ride):
    return RideEvent.objects.create(
        id_ride=sample_ride,
        description="Status changed to pickup",
        created_at=timezone.now() - timedelta(hours=25),
    )
