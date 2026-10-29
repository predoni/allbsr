"""
Business logic that doesn't belong in a view or a serializer.

Views decide *who* may do something and *how* to respond; serializers validate
input. The actual "what happens" for multi-step operations lives here, so the
same process can be triggered from several places (self-service endpoint,
admin endpoint, a future management command...) without duplicating it.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import AuthToken, PasswordResetToken, User


@transaction.atomic
def start_password_reset(user: User) -> PasswordResetToken:
    """
    The reset *process*:
      1. invalidate the current password (login is now impossible),
      2. revoke every active login token (existing sessions are logged out),
      3. cancel any earlier, still-open reset tokens,
      4. issue a fresh single-use token and email it to the user.
    """
    user.set_unusable_password()
    user.save(update_fields=['password'])

    AuthToken.objects.filter(user=user).delete()

    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
    token = PasswordResetToken.objects.create(user=user)

    send_mail(
        subject='Password reset',
        message=(
            'A password reset was requested for your account.\n'
            f'Use this token: {token.key}\n'
            f'It is valid for {int(PasswordResetToken.LIFETIME.total_seconds() // 3600)} hours '
            'and can be used once.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return token


@transaction.atomic
def complete_password_reset(token: PasswordResetToken, new_password: str) -> User:
    """Set the new password and burn the token."""
    user = token.user
    user.set_password(new_password)
    user.save(update_fields=['password'])

    token.used_at = timezone.now()
    token.save(update_fields=['used_at'])
    return user
