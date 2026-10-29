"""
Promote a user to admin from the command line:

    python manage.py make_admin ana@example.com

Management commands are the standard place for one-off operational tasks that
should NOT be exposed through the API.
"""
from django.core.management.base import BaseCommand, CommandError

from api.users.models import User


class Command(BaseCommand):
    help = "Give a user admin rights"

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        email = options["email"]
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user with email {email!r}")

        user.is_admin = True
        user.save(update_fields=["is_admin"])
        self.stdout.write(self.style.SUCCESS(f"{email} is now an admin"))
