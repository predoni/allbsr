"""
Data migration: make sure the default admin account exists.

Runs once, as part of `python manage.py migrate`, on every database (local,
test, production). `get_or_create` makes it safe to re-run, and it never
overwrites the password if the account already exists (so changing the admin
password later is not undone by a deploy).
"""
from django.contrib.auth.hashers import make_password
from django.db import migrations

DEFAULT_ADMIN_EMAIL = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin'


def create_default_admin(apps, schema_editor):
    # Always use apps.get_model() in migrations, never a direct import: this
    # gives the model *as it was at this migration*, not today's version.
    User = apps.get_model('api', 'User')
    User.objects.get_or_create(
        email=DEFAULT_ADMIN_EMAIL,
        defaults={'password': make_password(DEFAULT_ADMIN_PASSWORD), 'is_admin': True},
    )


def remove_default_admin(apps, schema_editor):
    User = apps.get_model('api', 'User')
    User.objects.filter(email=DEFAULT_ADMIN_EMAIL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_passwordresettoken'),
    ]

    operations = [
        migrations.RunPython(create_default_admin, reverse_code=remove_default_admin),
    ]
