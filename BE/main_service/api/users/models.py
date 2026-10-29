from datetime import timedelta

from django.contrib.auth import hashers
from django.db import models
from django.utils import timezone
import secrets
import uuid

# Create your models here.
class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)
    is_company = models.BooleanField(default=False)
    # Admins bypass the "only yourself" permission rules. Not settable through
    # the API - use `python manage.py make_admin <email>`.
    is_admin = models.BooleanField(default=False)
    details = models.OneToOneField('UserDetails', on_delete=models.CASCADE, null=True, blank=True)
    company_details = models.OneToOneField('CompanyDetails', on_delete=models.CASCADE, null=True, blank=True)

    # DRF's permission classes (e.g. IsAuthenticated) look at these on request.user.
    # Django's own auth User gets them for free; our custom model has to declare them.
    is_authenticated = True
    is_anonymous = False

    # Same names as Django's built-in user, so the API feels familiar.
    def set_password(self, raw_password):
        self.password = hashers.make_password(raw_password)

    def set_unusable_password(self):
        # Stores a marker that can never match any input -> login is impossible
        # until a new password is set through the reset process.
        self.password = hashers.make_password(None)

    def check_password(self, raw_password):
        return hashers.check_password(raw_password, self.password)

    def __str__(self):
        return self.email

class UserDetails(models.Model):
    #user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='details')
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class CompanyDetails(models.Model):
    #user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='company_details')
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255)
    company_address = models.TextField(blank=True, null=True)
    company_phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.company_name

class AuthToken(models.Model):
    """Opaque API token. The client sends it as `Authorization: Token <key>`."""
    key = models.CharField(max_length=40, primary_key=True, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='auth_token')
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(20)  # 40 hex chars, cryptographically random
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"token for {self.user.email}"


class PasswordResetToken(models.Model):
    """
    One-time, time-limited token proving the holder may set a new password.
    Issued by the reset process; delivered to the user by email (or by an admin).
    """
    LIFETIME = timedelta(hours=24)

    key = models.CharField(max_length=64, primary_key=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    created = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_urlsafe(32)
        return super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.used_at is None and timezone.now() - self.created < self.LIFETIME

    def __str__(self):
        return f"reset token for {self.user.email}"
