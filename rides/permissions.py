"""Custom DRF permissions."""

from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Grant access only to authenticated users with ``role == 'admin'``.

    - Unauthenticated requests -> DRF returns HTTP 401.
    - Authenticated non-admin requests -> DRF returns HTTP 403.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(request.user, "role", None) == "admin"
