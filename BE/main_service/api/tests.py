"""
Tests for the `api` app.

How Django tests work
---------------------
* Run them with:            python manage.py test
* Run one class:            python manage.py test api.tests.UserApiTests
* Run one test:             python manage.py test api.tests.UserApiTests.test_create_user
* Verbose output:           python manage.py test -v 2

Django creates a brand-new, empty test database for every run (it never
touches db.sqlite3), runs every method whose name starts with `test_`,
and rolls the database back between tests so they don't affect each other.

Each test follows the same 3 steps: Arrange (set up data), Act (call the
API), Assert (check the result).
"""
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .users.models import CompanyDetails, User, UserDetails


# --------------------------------------------------------------------------
# Model tests - check the database layer on its own, no HTTP involved.
# --------------------------------------------------------------------------
class UserModelTests(APITestCase):
    def test_user_str_is_email(self):
        user = User.objects.create(email="ana@example.com", password="secret")
        self.assertEqual(str(user), "ana@example.com")

    def test_user_defaults(self):
        user = User.objects.create(email="ana@example.com", password="secret")
        self.assertFalse(user.is_company)
        self.assertIsNone(user.details)
        self.assertIsNone(user.company_details)
        self.assertIsNotNone(user.id)  # UUID is generated automatically

    def test_email_must_be_unique(self):
        from django.db import IntegrityError

        User.objects.create(email="ana@example.com", password="secret")
        with self.assertRaises(IntegrityError):
            User.objects.create(email="ana@example.com", password="other")

    def test_user_details_str(self):
        details = UserDetails.objects.create(first_name="Ana", last_name="Popescu")
        self.assertEqual(str(details), "Ana Popescu")

    def test_company_details_str(self):
        company = CompanyDetails.objects.create(company_name="ACME SRL")
        self.assertEqual(str(company), "ACME SRL")


# --------------------------------------------------------------------------
# API tests - go through the real URLs and views, exactly like a client would.
# --------------------------------------------------------------------------
class UserApiTests(APITestCase):
    # Your router is mounted at api/users/ and registers 'users', so the
    # list endpoint is /api/users/users/ and the detail is /api/users/users/<id>/
    LIST_URL = "/api/users/users/"

    def detail_url(self, user_id):
        return f"{self.LIST_URL}{user_id}/"

    def setUp(self):
        # Since the permissions task, reading/updating users requires a login.
        # `self.me` is the logged-in user for every test in this class; tests that
        # check the anonymous path call self.client.force_authenticate(user=None).
        self.me = User.objects.create(email="me@example.com", password="x")
        self.client.force_authenticate(user=self.me)

    def test_list_users(self):
        response = self.client.get(self.LIST_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [u["email"] for u in response.json()]
        self.assertIn("me@example.com", emails)
        self.assertIn("admin", emails)  # the seeded default admin is always there

    def test_create_user(self):
        self.client.force_authenticate(user=None)  # registration is anonymous
        payload = {"email": "ana@example.com", "password": "secret123"}

        response = self.client.post(self.LIST_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["email"], "ana@example.com")
        self.assertTrue(User.objects.filter(email="ana@example.com").exists())

    def test_password_is_never_returned_in_responses(self):
        user = User.objects.create(email="ana@example.com", password="secret")

        list_response = self.client.get(self.LIST_URL)
        detail_response = self.client.get(self.detail_url(user.id))
        create_response = self.client.post(
            self.LIST_URL, {"email": "bob@example.com", "password": "x"}, format="json"
        )

        for item in list_response.json():
            self.assertNotIn("password", item)
        self.assertNotIn("password", detail_response.json())
        self.assertNotIn("password", create_response.json())

    def test_password_is_still_required_on_create(self):
        response = self.client.post(
            self.LIST_URL, {"email": "ana@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.json())

    def test_password_is_hashed_on_create(self):
        from django.contrib.auth.hashers import check_password

        self.client.post(
            self.LIST_URL, {"email": "ana@example.com", "password": "secret123"}, format="json"
        )

        user = User.objects.get(email="ana@example.com")
        self.assertNotEqual(user.password, "secret123")          # not stored as plain text
        self.assertTrue(check_password("secret123", user.password))  # but still verifiable

    def test_password_is_hashed_on_update(self):
        from django.contrib.auth.hashers import check_password

        user = self.me

        self.client.patch(self.detail_url(user.id), {"password": "new-pass"}, format="json")

        user.refresh_from_db()
        self.assertNotEqual(user.password, "new-pass")
        self.assertTrue(check_password("new-pass", user.password))

    def test_update_without_password_keeps_existing_hash(self):
        from django.contrib.auth.hashers import check_password

        self.client.post(
            self.LIST_URL, {"email": "ana@example.com", "password": "secret123"}, format="json"
        )
        user = User.objects.get(email="ana@example.com")
        self.client.force_authenticate(user=user)  # act as the user we just registered

        self.client.patch(self.detail_url(user.id), {"is_company": True}, format="json")

        user.refresh_from_db()
        self.assertTrue(check_password("secret123", user.password))  # not re-hashed / wiped

    def test_create_user_with_invalid_email_fails(self):
        payload = {"email": "not-an-email", "password": "secret123"}

        response = self.client.post(self.LIST_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())
        self.assertFalse(User.objects.filter(email="not-an-email").exists())

    def test_create_user_with_duplicate_email_fails(self):
        User.objects.create(email="ana@example.com", password="secret")

        response = self.client.post(
            self.LIST_URL, {"email": "ana@example.com", "password": "x"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_user(self):
        user = User.objects.create(email="ana@example.com", password="secret")

        response = self.client.get(self.detail_url(user.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], str(user.id))

    def test_retrieve_missing_user_returns_404(self):
        import uuid

        response = self.client.get(self.detail_url(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_user(self):
        user = self.me

        response = self.client.patch(
            self.detail_url(user.id), {"is_company": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()  # reload from DB to see what the view saved
        self.assertTrue(user.is_company)

    def test_delete_user(self):
        user = self.me

        response = self.client.delete(self.detail_url(user.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    # ---- nested details: one request creates the user AND their details ----

    def test_register_with_nested_details(self):
        self.client.force_authenticate(user=None)
        payload = {
            "email": "ana@example.com",
            "password": "secret123",
            "details": {"first_name": "Ana", "last_name": "Popescu", "phone_number": "0712"},
        }

        response = self.client.post(self.LIST_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="ana@example.com")
        self.assertEqual(user.details.first_name, "Ana")
        self.assertEqual(response.json()["details"]["last_name"], "Popescu")  # nested in response too

    def test_register_company_with_nested_company_details(self):
        self.client.force_authenticate(user=None)
        payload = {
            "email": "acme@example.com",
            "password": "secret123",
            "is_company": True,
            "company_details": {"company_name": "ACME SRL"},
        }

        response = self.client.post(self.LIST_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="acme@example.com")
        self.assertEqual(user.company_details.company_name, "ACME SRL")
        self.assertIsNone(user.details)

    def test_register_without_details_is_fine(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.LIST_URL, {"email": "ana@example.com", "password": "secret123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.json()["details"])

    def test_register_with_invalid_nested_details_creates_nothing(self):
        self.client.force_authenticate(user=None)
        payload = {
            "email": "ana@example.com",
            "password": "secret123",
            "details": {"last_name": "Popescu"},  # first_name missing
        }

        response = self.client.post(self.LIST_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.json()["details"])
        self.assertFalse(User.objects.filter(email="ana@example.com").exists())
        self.assertEqual(UserDetails.objects.count(), 0)  # no orphaned details row

    def test_patch_nested_details_updates_in_place(self):
        details = UserDetails.objects.create(first_name="Ana", last_name="Popescu")
        self.me.details = details
        self.me.save()

        response = self.client.patch(
            self.detail_url(self.me.id), {"details": {"phone_number": "0799"}}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        details.refresh_from_db()
        self.assertEqual(details.phone_number, "0799")
        self.assertEqual(details.first_name, "Ana")  # untouched fields stay
        self.me.refresh_from_db()
        self.assertEqual(self.me.details_id, details.id)  # same row, not a new one

    def test_patch_nested_details_creates_if_missing(self):
        self.assertIsNone(self.me.details)

        response = self.client.patch(
            self.detail_url(self.me.id),
            {"details": {"first_name": "Ana", "last_name": "Popescu"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.me.refresh_from_db()
        self.assertEqual(self.me.details.first_name, "Ana")

    def test_patch_details_to_null_removes_them(self):
        details = UserDetails.objects.create(first_name="Ana", last_name="Popescu")
        self.me.details = details
        self.me.save()

        response = self.client.patch(self.detail_url(self.me.id), {"details": None}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.me.refresh_from_db()
        self.assertIsNone(self.me.details)
        self.assertFalse(UserDetails.objects.filter(pk=details.pk).exists())  # cleaned up


class UserDetailsApiTests(APITestCase):
    LIST_URL = "/api/users/user-details/"

    def setUp(self):
        self.client.force_authenticate(user=User.objects.create(email="me@example.com", password="x"))

    def test_create_user_details(self):
        payload = {"first_name": "Ana", "last_name": "Popescu", "phone_number": "0712345678"}

        response = self.client.post(self.LIST_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UserDetails.objects.count(), 1)

    def test_first_name_is_required(self):
        response = self.client.post(self.LIST_URL, {"last_name": "Popescu"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.json())


class CompanyDetailsApiTests(APITestCase):
    LIST_URL = "/api/users/company-details/"

    def setUp(self):
        self.client.force_authenticate(user=User.objects.create(email="me@example.com", password="x"))

    def test_create_company_details(self):
        response = self.client.post(
            self.LIST_URL, {"company_name": "ACME SRL"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CompanyDetails.objects.get().company_name, "ACME SRL")

    def test_list_company_details(self):
        CompanyDetails.objects.create(company_name="ACME SRL")
        CompanyDetails.objects.create(company_name="Globex")

        response = self.client.get(self.LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)


# --------------------------------------------------------------------------
# Authentication - login / logout / "who am I"
# --------------------------------------------------------------------------
class AuthApiTests(APITestCase):
    LOGIN_URL = "/api/users/login/"
    LOGOUT_URL = "/api/users/logout/"
    ME_URL = "/api/users/me/"

    def setUp(self):
        # setUp runs before EVERY test in this class - handy for shared fixtures.
        # We go through the API so the password gets hashed properly.
        cache.clear()  # login is rate-limited; counters live in the cache
        self.client.post(
            "/api/users/users/",
            {"email": "ana@example.com", "password": "secret123"},
            format="json",
        )
        self.user = User.objects.get(email="ana@example.com")

    def login(self, email="ana@example.com", password="secret123"):
        return self.client.post(
            self.LOGIN_URL, {"email": email, "password": password}, format="json"
        )

    def test_login_with_valid_credentials_returns_token(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn("token", body)
        self.assertEqual(body["user"]["email"], "ana@example.com")
        self.assertNotIn("password", body["user"])

    def test_login_twice_returns_same_token(self):
        first = self.login().json()["token"]
        second = self.login().json()["token"]
        self.assertEqual(first, second)

    def test_login_with_wrong_password_fails(self):
        response = self.login(password="wrong")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("token", response.json())

    def test_login_with_unknown_email_fails_with_same_error(self):
        # Same message for "no such user" and "wrong password", so an attacker
        # can't use the login form to discover which emails are registered.
        wrong_password = self.login(password="wrong").json()
        unknown_email = self.login(email="nobody@example.com").json()
        self.assertEqual(wrong_password, unknown_email)

    def test_me_without_token_is_unauthorized(self):
        response = self.client.get(self.ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_invalid_token_is_unauthorized(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        response = self.client.get(self.ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_token_returns_current_user(self):
        token = self.login().json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

        response = self.client.get(self.ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], str(self.user.id))

    def test_logout_invalidates_token(self):
        token = self.login().json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

        logout = self.client.post(self.LOGOUT_URL)
        after = self.client.get(self.ME_URL)

        self.assertEqual(logout.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(after.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_without_token_is_unauthorized(self):
        response = self.client.post(self.LOGOUT_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# --------------------------------------------------------------------------
# Permissions - who is allowed to do what
# --------------------------------------------------------------------------
class PermissionTests(APITestCase):
    USERS_URL = "/api/users/users/"

    def setUp(self):
        self.ana = User.objects.create(email="ana@example.com", password="x")
        self.bob = User.objects.create(email="bob@example.com", password="x")

    def as_user(self, user):
        # force_authenticate skips the token dance: the request simply *is* this user.
        self.client.force_authenticate(user=user)

    def test_anonymous_can_register(self):
        response = self.client.post(
            self.USERS_URL, {"email": "new@example.com", "password": "pw"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_anonymous_cannot_list_users(self):
        self.assertEqual(self.client.get(self.USERS_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_cannot_retrieve_user(self):
        response = self.client.get(f"{self.USERS_URL}{self.ana.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_list_and_retrieve(self):
        self.as_user(self.ana)
        self.assertEqual(self.client.get(self.USERS_URL).status_code, status.HTTP_200_OK)
        response = self.client.get(f"{self.USERS_URL}{self.bob.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_can_update_self(self):
        self.as_user(self.ana)
        response = self.client.patch(
            f"{self.USERS_URL}{self.ana.id}/", {"is_company": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_cannot_update_someone_else(self):
        self.as_user(self.ana)
        response = self.client.patch(
            f"{self.USERS_URL}{self.bob.id}/", {"is_company": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_company)

    def test_user_cannot_delete_someone_else(self):
        self.as_user(self.ana)
        response = self.client.delete(f"{self.USERS_URL}{self.bob.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(pk=self.bob.pk).exists())

    def test_user_can_delete_self(self):
        self.as_user(self.ana)
        response = self.client.delete(f"{self.USERS_URL}{self.ana.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_anonymous_cannot_create_details(self):
        response = self.client.post(
            "/api/users/user-details/", {"first_name": "A", "last_name": "B"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_edit_details_linked_to_someone_else(self):
        details = UserDetails.objects.create(first_name="Bob", last_name="B")
        self.bob.details = details
        self.bob.save()
        self.as_user(self.ana)

        response = self.client.patch(
            f"/api/users/user-details/{details.id}/", {"first_name": "Hacked"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_edit_own_details(self):
        details = UserDetails.objects.create(first_name="Ana", last_name="P")
        self.ana.details = details
        self.ana.save()
        self.as_user(self.ana)

        response = self.client.patch(
            f"/api/users/user-details/{details.id}/", {"first_name": "Anna"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_cannot_edit_company_details_linked_to_someone_else(self):
        company = CompanyDetails.objects.create(company_name="Bob Inc")
        self.bob.company_details = company
        self.bob.save()
        self.as_user(self.ana)

        response = self.client.patch(
            f"/api/users/company-details/{company.id}/", {"company_name": "Pwned"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# --------------------------------------------------------------------------
# Admins - an is_admin flag on User that bypasses the "only yourself" rules
# --------------------------------------------------------------------------
class AdminTests(APITestCase):
    USERS_URL = "/api/users/users/"

    def setUp(self):
        self.admin = User.objects.create(email="admin@example.com", password="x", is_admin=True)
        self.bob = User.objects.create(email="bob@example.com", password="x")

    def test_admin_can_update_other_users(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.USERS_URL}{self.bob.id}/", {"is_company": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_company)

    def test_admin_can_delete_other_users(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f"{self.USERS_URL}{self.bob.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.bob.pk).exists())

    def test_admin_can_edit_other_users_details(self):
        details = UserDetails.objects.create(first_name="Bob", last_name="B")
        self.bob.details = details
        self.bob.save()
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/users/user-details/{details.id}/", {"first_name": "Robert"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_is_admin_is_visible_in_responses(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/users/me/")
        self.assertTrue(response.json()["is_admin"])

    def test_user_cannot_make_themselves_admin(self):
        self.client.force_authenticate(user=self.bob)

        response = self.client.patch(
            f"{self.USERS_URL}{self.bob.id}/", {"is_admin": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)  # request is fine...
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_admin)  # ...but the field is silently ignored

    def test_cannot_register_as_admin(self):
        response = self.client.post(
            self.USERS_URL,
            {"email": "evil@example.com", "password": "x", "is_admin": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(User.objects.get(email="evil@example.com").is_admin)

    def test_make_admin_management_command(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("make_admin", "bob@example.com", stdout=out)

        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_admin)
        self.assertIn("bob@example.com", out.getvalue())

    def test_make_admin_with_unknown_email_fails(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command("make_admin", "nobody@example.com")


# --------------------------------------------------------------------------
# Seeded default admin + admin dashboard
# --------------------------------------------------------------------------
class SeededAdminTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_default_admin_exists_after_migrate(self):
        admin = User.objects.get(email="admin")
        self.assertTrue(admin.is_admin)
        self.assertTrue(admin.check_password("admin"))

    def test_default_admin_can_log_in(self):
        response = self.client.post(
            "/api/users/login/", {"email": "admin", "password": "admin"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["user"]["is_admin"])


class AdminDashboardTests(APITestCase):
    URL = "/api/users/admin/dashboard/"

    def setUp(self):
        self.admin = User.objects.get(email="admin")
        details = UserDetails.objects.create(first_name="Ana", last_name="Popescu")
        self.ana = User.objects.create(email="ana@example.com", password="x", details=details)
        company = CompanyDetails.objects.create(company_name="ACME")
        self.acme = User.objects.create(
            email="acme@example.com", password="x", is_company=True, company_details=company
        )

    def test_anonymous_is_unauthorized(self):
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_is_forbidden(self):
        self.client.force_authenticate(user=self.ana)
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_sees_totals_and_all_users_with_details(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["totals"], {"users": 3, "individuals": 2, "companies": 1, "admins": 1})
        by_email = {u["email"]: u for u in body["users"]}
        self.assertEqual(by_email["ana@example.com"]["details"]["first_name"], "Ana")
        self.assertEqual(by_email["acme@example.com"]["company_details"]["company_name"], "ACME")
        self.assertNotIn("password", by_email["ana@example.com"])


# --------------------------------------------------------------------------
# Password reset process
# --------------------------------------------------------------------------
class PasswordResetTests(APITestCase):
    REQUEST_URL = "/api/users/password-reset/"
    CONFIRM_URL = "/api/users/password-reset/confirm/"
    LOGIN_URL = "/api/users/login/"

    def setUp(self):
        cache.clear()  # reset + login are rate-limited; counters live in the cache
        self.client.post(
            "/api/users/users/", {"email": "ana@example.com", "password": "old-pass-1"}, format="json"
        )
        self.ana = User.objects.get(email="ana@example.com")

    def login(self, email="ana@example.com", password="old-pass-1"):
        return self.client.post(self.LOGIN_URL, {"email": email, "password": password}, format="json")

    def request_reset(self, email="ana@example.com"):
        return self.client.post(self.REQUEST_URL, {"email": email}, format="json")

    def latest_token_key(self):
        from django.core import mail
        # The token is delivered by email; in tests Django captures emails in mail.outbox.
        return mail.outbox[-1].body.split("token: ")[1].split()[0]

    # ---- requesting a reset ----

    def test_request_invalidates_old_password(self):
        self.assertEqual(self.login().status_code, status.HTTP_200_OK)  # works before

        self.request_reset()

        self.assertEqual(self.login().status_code, status.HTTP_400_BAD_REQUEST)  # not after

    def test_request_revokes_existing_login_tokens(self):
        token = self.login().json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.client.get("/api/users/me/").status_code, status.HTTP_200_OK)

        self.request_reset()

        self.assertEqual(self.client.get("/api/users/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_request_sends_email_with_token(self):
        from django.core import mail

        response = self.request_reset()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@example.com"])
        self.assertTrue(len(self.latest_token_key()) >= 32)

    def test_request_for_unknown_email_looks_identical(self):
        from django.core import mail

        known = self.request_reset()
        unknown = self.request_reset("nobody@example.com")

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())  # no hint whether the account exists
        self.assertEqual(len(mail.outbox), 1)            # ...but only one real email went out

    def test_new_request_invalidates_previous_reset_token(self):
        self.request_reset()
        first = self.latest_token_key()
        self.request_reset()

        response = self.client.post(
            self.CONFIRM_URL, {"token": first, "new_password": "new-pass-123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ---- confirming a reset ----

    def test_confirm_sets_new_password(self):
        self.request_reset()
        token = self.latest_token_key()

        response = self.client.post(
            self.CONFIRM_URL, {"token": token, "new_password": "new-pass-123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.login(password="old-pass-1").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.login(password="new-pass-123").status_code, status.HTTP_200_OK)

    def test_token_is_single_use(self):
        self.request_reset()
        token = self.latest_token_key()
        self.client.post(self.CONFIRM_URL, {"token": token, "new_password": "new-pass-123"}, format="json")

        again = self.client.post(
            self.CONFIRM_URL, {"token": token, "new_password": "other-pass-1"}, format="json"
        )

        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.login(password="new-pass-123").status_code, status.HTTP_200_OK)

    def test_confirm_with_bogus_token_fails(self):
        response = self.client.post(
            self.CONFIRM_URL, {"token": "nope", "new_password": "new-pass-123"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.json())

    def test_confirm_with_expired_token_fails(self):
        from datetime import timedelta

        from django.utils import timezone

        from .users.models import PasswordResetToken

        self.request_reset()
        reset = PasswordResetToken.objects.get(user=self.ana)
        PasswordResetToken.objects.filter(pk=reset.pk).update(
            created=timezone.now() - PasswordResetToken.LIFETIME - timedelta(minutes=1)
        )

        response = self.client.post(
            self.CONFIRM_URL, {"token": reset.key, "new_password": "new-pass-123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_rejects_short_password(self):
        self.request_reset()
        response = self.client.post(
            self.CONFIRM_URL, {"token": self.latest_token_key(), "new_password": "short"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.json())

    # ---- admin-initiated reset ----

    def admin_reset_url(self, user):
        return f"/api/users/users/{user.id}/reset-password/"

    def test_admin_can_reset_any_users_password(self):
        from django.core import mail

        self.client.force_authenticate(user=User.objects.get(email="admin"))

        response = self.client.post(self.admin_reset_url(self.ana))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.json())  # admin can hand the token to the user directly
        self.assertEqual(len(mail.outbox), 1)     # ...and it was emailed as well
        self.client.force_authenticate(user=None)
        self.assertEqual(self.login().status_code, status.HTTP_400_BAD_REQUEST)  # old pw dead

        confirm = self.client.post(
            self.CONFIRM_URL,
            {"token": response.json()["token"], "new_password": "new-pass-123"},
            format="json",
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)

    def test_regular_user_cannot_admin_reset_others(self):
        bob = User.objects.create(email="bob@example.com", password="x")
        self.client.force_authenticate(user=self.ana)

        response = self.client.post(self.admin_reset_url(bob))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_admin_reset(self):
        response = self.client.post(self.admin_reset_url(self.ana))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# --------------------------------------------------------------------------
# Rate limiting on the anonymous endpoints
# --------------------------------------------------------------------------
class ThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create(email="ana@example.com", password="x")

    def tearDown(self):
        cache.clear()  # don't leak our exhausted counters into other test classes

    def test_password_reset_requests_are_rate_limited(self):
        from django.core import mail

        responses = [
            self.client.post("/api/users/password-reset/", {"email": "ana@example.com"}, format="json")
            for _ in range(4)
        ]

        self.assertEqual([r.status_code for r in responses[:3]], [200, 200, 200])
        self.assertEqual(responses[3].status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", responses[3].headers)
        self.assertEqual(len(mail.outbox), 3)  # the throttled request did nothing

    def test_login_attempts_are_rate_limited(self):
        responses = [
            self.client.post(
                "/api/users/login/", {"email": "ana@example.com", "password": "guess"}, format="json"
            )
            for _ in range(11)
        ]

        self.assertTrue(all(r.status_code == 400 for r in responses[:10]))
        self.assertEqual(responses[10].status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_confirm_endpoint_is_rate_limited_too(self):
        # Otherwise an attacker could brute-force reset tokens.
        responses = [
            self.client.post(
                "/api/users/password-reset/confirm/",
                {"token": f"guess-{i}", "new_password": "whatever-123"},
                format="json",
            )
            for i in range(11)
        ]
        self.assertEqual(responses[10].status_code, status.HTTP_429_TOO_MANY_REQUESTS)
