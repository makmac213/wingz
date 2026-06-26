"""django-filter FilterSets.

Note: the Ride list endpoint performs its filtering manually inside
``RideViewSet.get_queryset`` so that invalid ``status`` / ``rider_email`` values
return a precise HTTP 400. This FilterSet is provided for declarative
documentation and reuse, and is wired into the RideEvent endpoint.
"""

import django_filters

from .models import Ride, RideEvent


class RideFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    rider_email = django_filters.CharFilter(
        field_name="id_rider__email", lookup_expr="iexact"
    )

    class Meta:
        model = Ride
        fields = ["status", "rider_email"]


class RideEventFilter(django_filters.FilterSet):
    ride = django_filters.NumberFilter(field_name="id_ride_id")

    class Meta:
        model = RideEvent
        fields = ["ride"]
