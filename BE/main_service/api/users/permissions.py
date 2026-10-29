from rest_framework.permissions import SAFE_METHODS, BasePermission

# SAFE_METHODS = GET, HEAD, OPTIONS - i.e. reads. Everything else is a write.


class IsSelfOrReadOnly(BasePermission):
    """Anyone logged in may read users; a user may only modify/delete *themselves*.
    Admins may modify anyone."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS or request.user.is_admin:
            return True
        return obj == request.user


class OwnsDetailsOrReadOnly(BasePermission):
    """
    For UserDetails / CompanyDetails rows: reads are open to logged-in users,
    writes only if the row is the one linked to the requesting user.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in SAFE_METHODS or user.is_admin:
            return True
        return obj == user.details or obj == user.company_details


class IsAdmin(BasePermission):
    """Endpoint-level: only admins get in at all (combine with IsAuthenticated)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_admin)
