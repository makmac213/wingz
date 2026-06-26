"""Serializers for User, Ride, and RideEvent."""

from rest_framework import serializers

from .models import Ride, RideEvent, User


class UserSerializer(serializers.ModelSerializer):
    """User serializer. ``password`` is write-only and never returned."""

    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id_user",
            "role",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "password",
        ]

    def validate_role(self, value):
        valid_roles = [r[0] for r in User.ROLE_CHOICES]
        if value not in valid_roles:
            raise serializers.ValidationError(
                f"Role must be one of: {', '.join(valid_roles)}"
            )
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RideEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideEvent
        fields = ["id_ride_event", "id_ride", "description", "created_at"]


class _CoordinateValidationMixin:
    """Shared latitude/longitude range validation."""

    def validate_pickup_latitude(self, value):
        return self._validate_latitude(value)

    def validate_dropoff_latitude(self, value):
        return self._validate_latitude(value)

    def validate_pickup_longitude(self, value):
        return self._validate_longitude(value)

    def validate_dropoff_longitude(self, value):
        return self._validate_longitude(value)

    @staticmethod
    def _validate_latitude(value):
        if not (-90 <= value <= 90):
            raise serializers.ValidationError(
                "Latitude must be between -90 and 90."
            )
        return value

    @staticmethod
    def _validate_longitude(value):
        if not (-180 <= value <= 180):
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180."
            )
        return value


class RideListSerializer(serializers.ModelSerializer):
    """List representation: nested users + the prefetched ``todays_ride_events``.

    ``todays_ride_events`` is sourced from the ``to_attr`` populated by the
    Prefetch in ``RideViewSet.get_queryset`` — reading it triggers no query.
    """

    id_rider = UserSerializer(read_only=True)
    id_driver = UserSerializer(read_only=True)
    todays_ride_events = RideEventSerializer(many=True, read_only=True)

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
            "id_rider",
            "id_driver",
            "todays_ride_events",
        ]


class RideDetailSerializer(_CoordinateValidationMixin, serializers.ModelSerializer):
    """Detail / write representation: nested users (read) + writable FK ids +
    the full all-time ``ride_events`` list.
    """

    id_rider = UserSerializer(read_only=True)
    id_driver = UserSerializer(read_only=True)
    ride_events = RideEventSerializer(source="events", many=True, read_only=True)

    id_rider_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="id_rider", write_only=True
    )
    id_driver_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="id_driver", write_only=True
    )

    class Meta:
        model = Ride
        fields = [
            "id_ride",
            "status",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_latitude",
            "dropoff_longitude",
            "pickup_time",
            "id_rider",
            "id_driver",
            "id_rider_id",
            "id_driver_id",
            "ride_events",
        ]
