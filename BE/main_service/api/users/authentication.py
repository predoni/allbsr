from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from .models import AuthToken


class UserTokenAuthentication(TokenAuthentication):
    """
    Reads `Authorization: Token <key>` and resolves it to one of *our* users.

    DRF's built-in TokenAuthentication assumes Django's auth User model; we only
    override the lookup step so it works with api.users.models.User instead.
    """

    def authenticate_credentials(self, key):
        try:
            token = AuthToken.objects.select_related('user').get(key=key)
        except AuthToken.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')
        return (token.user, token)  # becomes request.user and request.auth
