from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class HomepageTests(TestCase):
    def test_homepage_renders(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Iron Quill Games Studio")

    def test_homepage_contains_concealed_staff_entry(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'data-staff-entry-url="/studio-access/"')


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class StaffAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="staff",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="player",
            password="correct-horse-battery-staple",
        )

    def test_triage_redirects_anonymous_user_to_staff_login(self):
        response = self.client.get(reverse("feedback-triage"))

        self.assertRedirects(
            response,
            f'{reverse("staff-login")}?next={reverse("feedback-triage")}',
        )

    def test_staff_user_can_open_triage(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("feedback-triage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Feedback Triage")

    def test_staff_login_redirects_to_triage(self):
        response = self.client.post(
            reverse("staff-login"),
            {
                "username": self.staff_user.username,
                "password": "correct-horse-battery-staple",
            },
        )

        self.assertRedirects(response, reverse("feedback-triage"))

    def test_non_staff_user_cannot_sign_in_to_staff_workspace(self):
        response = self.client.post(
            reverse("staff-login"),
            {
                "username": self.regular_user.username,
                "password": "correct-horse-battery-staple",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This account does not have staff access.")

    def test_staff_user_can_log_out(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(reverse("staff-logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_maintenance_admin_uses_relocated_url(self):
        self.client.force_login(self.staff_user)

        response = self.client.get("/studio-maintenance/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Site administration")

    def test_default_admin_url_is_not_exposed(self):
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 404)

    @override_settings(AXES_FAILURE_LIMIT=2)
    def test_repeated_login_failures_lock_staff_username(self):
        credentials = {
            "username": self.staff_user.username,
            "password": "incorrect-password",
        }

        self.client.post(reverse("staff-login"), credentials)
        response = self.client.post(reverse("staff-login"), credentials)

        self.assertEqual(response.status_code, 429)
