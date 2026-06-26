"""ViewSets, token endpoint, and the custom exception handler.

The Ride list endpoint is the performance-critical path. It is engineered to
execute at most 3 SQL queries regardless of page size:
  1. COUNT (pagination)
  2. SELECT rides JOIN rider JOIN driver  (select_related)
  3. SELECT today's ride events           (Prefetch with date predicate)
"""

from datetime import timedelta

from django.db.models import (
    ExpressionWrapper,
    F,
    FloatField,
    Prefetch,
    Value,
)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import ACos, Cos, Radians, Sin
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .filters import RideEventFilter
from .models import Ride, RideEvent, User
from .serializers import (
    RideDetailSerializer,
    RideEventSerializer,
    RideListSerializer,
    UserSerializer,
)

# Earth radius in kilometres, used by the Haversine annotation.
EARTH_RADIUS_KM = 6371.0

# Coordinate bounds (defensive validation of query params).
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0

# How far back the "today's events" Prefetch window reaches.
RECENT_EVENTS_WINDOW_HOURS = 24


def custom_exception_handler(exc, context):
    """Ensure every error is JSON — never an HTML error page.

    DRF's default handler covers all APIException subclasses (400/401/403/404).
    Anything it does not recognise (a genuine 500) is wrapped here so clients
    always receive a structured JSON body.
    """
    response = exception_handler(exc, context)
    if response is not None:
        return response
    return Response(
        {"error": "An internal server error occurred."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def build_distance_annotation(lat, lon):
    """Return an ExpressionWrapper computing great-circle distance (km) from
    (lat, lon) to each ride's pickup point via the Haversine formula.

    All inputs are wrapped in ``Value`` so the SQL is fully parameterised
    (no string interpolation -> no SQL injection surface).
    """
    return ExpressionWrapper(
        Value(EARTH_RADIUS_KM)
        * ACos(
            Cos(Radians(Value(lat)))
            * Cos(Radians(F("pickup_latitude")))
            * Cos(Radians(F("pickup_longitude")) - Radians(Value(lon)))
            + Sin(Radians(Value(lat))) * Sin(Radians(F("pickup_latitude")))
        ),
        output_field=FloatField(),
    )


class AdminTokenObtainView(ObtainAuthToken):
    """POST /api/v1/auth/token/ — obtain an auth token from email + password.

    This endpoint is intentionally open (AllowAny); the credentials themselves
    are the gate. Admin-role enforcement happens on every other endpoint.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class UserViewSet(viewsets.ModelViewSet):
    """Full CRUD for users."""

    queryset = User.objects.all().order_by("id_user")
    serializer_class = UserSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"error": "Cannot delete user referenced by existing rides."},
                status=status.HTTP_409_CONFLICT,
            )


class RideViewSet(viewsets.ModelViewSet):
    """Full CRUD for rides, plus the filtered/sorted/paginated list endpoint."""

    def get_serializer_class(self):
        if self.action == "list":
            return RideListSerializer
        return RideDetailSerializer

    def get_queryset(self):
        cutoff = timezone.now() - timedelta(hours=RECENT_EVENTS_WINDOW_HOURS)

        todays_events_prefetch = Prefetch(
            "events",
            queryset=RideEvent.objects.filter(created_at__gte=cutoff),
            to_attr="todays_ride_events",
        )

        qs = (
            Ride.objects.select_related("id_rider", "id_driver")
            .prefetch_related(todays_events_prefetch)
        )

        # Filters and sorting only apply to the list action. For detail/CRUD
        # actions we return the base (prefetched) queryset so retrieve/update
        # still resolve by pk without touching query params.
        if self.action != "list":
            return qs

        qs = self._apply_filters(qs)
        qs = self._apply_sorting(qs)
        return qs

    # -- list helpers -------------------------------------------------------

    def _apply_filters(self, qs):
        params = self.request.query_params

        status_param = params.get("status")
        if status_param:
            valid = [s[0] for s in Ride.STATUS_CHOICES]
            if status_param not in valid:
                raise ValidationError(
                    {
                        "status": (
                            "Invalid status. Must be one of: "
                            f"{', '.join(valid)}"
                        )
                    }
                )
            qs = qs.filter(status=status_param)

        rider_email = params.get("rider_email")
        if rider_email:
            if not self._looks_like_email(rider_email):
                raise ValidationError(
                    {"rider_email": "Enter a valid email address."}
                )
            qs = qs.filter(id_rider__email__iexact=rider_email)

        return qs

    def _apply_sorting(self, qs):
        params = self.request.query_params
        lat_param = params.get("lat")
        lon_param = params.get("lon")

        # Neither provided -> default pickup_time ascending (id_ride tiebreak).
        if lat_param is None and lon_param is None:
            return qs.order_by("pickup_time", "id_ride")

        # Exactly one provided -> 400.
        if lat_param is None or lon_param is None:
            raise ValidationError(
                {"error": "Both lat and lon are required for distance sorting."}
            )

        try:
            lat = float(lat_param)
            lon = float(lon_param)
        except (TypeError, ValueError):
            raise ValidationError(
                {"error": "lat and lon must be numeric values."}
            )

        if not (LAT_MIN <= lat <= LAT_MAX) or not (LON_MIN <= lon <= LON_MAX):
            raise ValidationError(
                {
                    "error": (
                        "lat must be between -90 and 90; "
                        "lon must be between -180 and 180."
                    )
                }
            )

        return qs.annotate(
            distance=build_distance_annotation(lat, lon)
        ).order_by("distance", "id_ride")

    @staticmethod
    def _looks_like_email(value):
        # Cheap structural check; the unique email index does the real work.
        # Avoids accepting obvious junk / injection payloads as a "filter".
        return "@" in value and "." in value.split("@")[-1] and " " not in value


class RideEventViewSet(viewsets.ModelViewSet):
    """Full CRUD for ride events, filterable by ride."""

    serializer_class = RideEventSerializer
    filterset_class = RideEventFilter

    def get_queryset(self):
        return RideEvent.objects.all().order_by("id_ride_event")
