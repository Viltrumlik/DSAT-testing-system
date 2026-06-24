from rest_framework.permissions import BasePermission


class IsAuthenticatedAndNotFrozen(BasePermission):
    """
    Allow authenticated users, but block frozen students from API actions.
    """

    message = "Your account is frozen. Contact an administrator."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        role = str(getattr(user, "role", "") or "").strip().lower()
        if role == "student" and getattr(user, "is_frozen", False):
            return False
        return True
