"""App URL routing."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminTokenObtainView,
    RideEventViewSet,
    RideViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"rides", RideViewSet, basename="ride")
router.register(r"events", RideEventViewSet, basename="rideevent")

urlpatterns = [
    path("auth/token/", AdminTokenObtainView.as_view(), name="token-obtain"),
    path("", include(router.urls)),
]
