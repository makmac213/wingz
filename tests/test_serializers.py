"""Serializer-level validation tests."""

import pytest

from rides.serializers import RideDetailSerializer, UserSerializer


@pytest.mark.django_db
def test_user_serializer_password_not_in_output(rider_user):
    data = UserSerializer(rider_user).data
    assert "password" not in data


@pytest.mark.django_db
def test_user_serializer_invalid_role():
    serializer = UserSerializer(
        data={
            "role": "superuser",
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.com",
            "phone_number": "+1",
        }
    )
    assert not serializer.is_valid()
    assert "role" in serializer.errors


@pytest.mark.django_db
def test_user_serializer_phone_number_required():
    """BRD FR-004: phone_number omitted from payload must fail validation."""
    serializer = UserSerializer(
        data={
            "role": "rider",
            "first_name": "A",
            "last_name": "B",
            "email": "c@d.com",
        }
    )
    assert not serializer.is_valid()
    assert "phone_number" in serializer.errors


@pytest.mark.django_db
def test_user_serializer_phone_number_blank_rejected():
    """BRD FR-004: empty-string phone_number must fail validation."""
    serializer = UserSerializer(
        data={
            "role": "rider",
            "first_name": "A",
            "last_name": "B",
            "email": "e@f.com",
            "phone_number": "",
        }
    )
    assert not serializer.is_valid()
    assert "phone_number" in serializer.errors


@pytest.mark.parametrize(
    "field,value,valid",
    [
        ("pickup_latitude", 91.0, False),
        ("pickup_latitude", 90.0, True),
        ("pickup_latitude", -90.0, True),
        ("pickup_longitude", 181.0, False),
        ("pickup_longitude", 180.0, True),
        ("pickup_longitude", -180.0, True),
        ("dropoff_latitude", -90.001, False),
        ("dropoff_longitude", 180.001, False),
    ],
)
@pytest.mark.django_db
def test_coordinate_bounds(field, value, valid, rider_user, driver_user):
    payload = {
        "status": "en-route",
        "id_rider_id": rider_user.id_user,
        "id_driver_id": driver_user.id_user,
        "pickup_latitude": 1.0,
        "pickup_longitude": 1.0,
        "dropoff_latitude": 1.0,
        "dropoff_longitude": 1.0,
        "pickup_time": "2026-06-26T00:00:00Z",
    }
    payload[field] = value
    serializer = RideDetailSerializer(data=payload)
    is_valid = serializer.is_valid()
    assert is_valid is valid
    if not valid:
        assert field in serializer.errors


@pytest.mark.django_db
def test_ride_invalid_status(rider_user, driver_user):
    serializer = RideDetailSerializer(
        data={
            "status": "cancelled",
            "id_rider_id": rider_user.id_user,
            "id_driver_id": driver_user.id_user,
            "pickup_latitude": 1.0,
            "pickup_longitude": 1.0,
            "dropoff_latitude": 1.0,
            "dropoff_longitude": 1.0,
            "pickup_time": "2026-06-26T00:00:00Z",
        }
    )
    assert not serializer.is_valid()
    assert "status" in serializer.errors


@pytest.mark.django_db
def test_ride_nonexistent_rider(driver_user):
    serializer = RideDetailSerializer(
        data={
            "status": "en-route",
            "id_rider_id": 999999,
            "id_driver_id": driver_user.id_user,
            "pickup_latitude": 1.0,
            "pickup_longitude": 1.0,
            "dropoff_latitude": 1.0,
            "dropoff_longitude": 1.0,
            "pickup_time": "2026-06-26T00:00:00Z",
        }
    )
    assert not serializer.is_valid()
    assert "id_rider_id" in serializer.errors
