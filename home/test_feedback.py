import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import FeedbackIngestRejection, FeedbackReport, Issue, Tag


def valid_payload(feedback_id="feedback-001", with_save=False):
    save_snapshot = None
    save_schema_version = 0
    save_snapshot_filename = ""
    if with_save:
        save_schema_version = 1
        save_snapshot_filename = "save_snapshot.json"
        save_snapshot = {
            "schema_version": 1,
            "created_at_utc": "2026-05-30T12:00:00Z",
            "updated_at_utc": "2026-05-30T12:01:00Z",
            "run_uuid": "run-001",
            "save_sequence_number": 1,
            "save_reason": "player_feedback",
            "run_manager_snapshot": {"state": "playing"},
            "game_manager_snapshot": {},
            "player_state_snapshot": {"health": 3},
            "board_state_snapshot": {},
            "map_generation_snapshot": {},
        }
    return {
        "manifest": {
            "feedback_schema_version": 1,
            "feedback_id": feedback_id,
            "created_at_utc": "2026-05-30T12:34:56Z",
            "game_version": "0.1.0",
            "build_channel": "demo",
            "platform": "Windows",
            "locale": "en_GB",
            "feedback_policy_version": 1,
            "feedback_consent_timestamp_utc": "2026-05-30T12:30:00Z",
            "has_save_snapshot": with_save,
            "save_snapshot_filename": save_snapshot_filename,
            "save_schema_version": save_schema_version,
        },
        "message": "The movement choice was unclear :scream:",
        "save_snapshot": save_snapshot,
    }


class FeedbackReceiverTests(TestCase):
    def post_payload(self, payload, content_type="application/json"):
        return self.client.post(
            reverse("game-feedback-v1"),
            data=json.dumps(payload),
            content_type=content_type,
        )

    def test_valid_report_without_save_is_accepted(self):
        response = self.post_payload(valid_payload())

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["accepted"])
        self.assertEqual(response["Cache-Control"], "no-store")
        report = FeedbackReport.objects.get()
        self.assertEqual(report.feedback_id, "feedback-001")
        self.assertEqual(report.message, "The movement choice was unclear :scream:")
        self.assertEqual(report.normalized_message, "the movement choice was unclear :scream:")
        self.assertIsNone(report.save_snapshot)

    def test_duplicate_feedback_id_returns_existing_receipt(self):
        first_response = self.post_payload(valid_payload())
        second_response = self.post_payload(valid_payload())

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.json()["receipt_id"], second_response.json()["receipt_id"])
        self.assertEqual(FeedbackReport.objects.count(), 1)

    def test_valid_save_snapshot_is_stored_privately(self):
        response = self.post_payload(valid_payload(with_save=True))

        self.assertEqual(response.status_code, 201)
        report = FeedbackReport.objects.get()
        self.assertTrue(report.has_save_snapshot)
        self.assertEqual(report.save_snapshot["run_uuid"], "run-001")

    def test_wrong_content_type_is_rejected(self):
        response = self.post_payload(valid_payload(), content_type="text/plain")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FeedbackReport.objects.count(), 0)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "unsupported_content_type")

    def test_unsupported_feedback_schema_is_rejected(self):
        payload = valid_payload()
        payload["manifest"]["feedback_schema_version"] = 2

        response = self.post_payload(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "unsupported_feedback_schema")

    def test_oversized_message_is_rejected(self):
        payload = valid_payload()
        payload["message"] = "x" * 2001

        response = self.post_payload(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "message_too_large")

    @override_settings(FEEDBACK_MAX_REQUEST_BYTES=100)
    def test_oversized_request_is_rejected(self):
        response = self.post_payload(valid_payload())

        self.assertEqual(response.status_code, 413)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "request_too_large")

    def test_save_snapshot_shape_is_validated(self):
        payload = valid_payload(with_save=True)
        payload["save_snapshot"]["run_uuid"] = ""

        response = self.post_payload(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "invalid_run_uuid")

    @override_settings(FEEDBACK_MAX_SAVE_BYTES=100)
    def test_oversized_save_snapshot_is_rejected(self):
        payload = valid_payload(with_save=True)
        payload["save_snapshot"]["board_state_snapshot"] = {"content": "x" * 200}

        response = self.post_payload(payload)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "save_snapshot_too_large")

    def test_excessive_json_nesting_is_rejected(self):
        payload = valid_payload(with_save=True)
        nested = {}
        cursor = nested
        for _ in range(35):
            cursor["child"] = {}
            cursor = cursor["child"]
        payload["save_snapshot"]["board_state_snapshot"] = nested

        response = self.post_payload(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FeedbackIngestRejection.objects.get().reason_code, "json_too_complex")

    @override_settings(FEEDBACK_GLOBAL_REQUESTS_PER_MINUTE=1)
    def test_global_rate_limit_rejects_excess_request(self):
        first_response = self.post_payload(valid_payload("feedback-001"))
        second_response = self.post_payload(valid_payload("feedback-002"))

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 429)
        self.assertEqual(FeedbackIngestRejection.objects.count(), 0)


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
class FeedbackSaveDownloadTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="staff-download",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        response = self.client.post(
            reverse("game-feedback-v1"),
            data=json.dumps(valid_payload(with_save=True)),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.report = FeedbackReport.objects.get()

    def test_anonymous_download_redirects_to_login(self):
        response = self.client.get(
            reverse("feedback-save-download", kwargs={"receipt_id": self.report.receipt_id}),
        )

        self.assertRedirects(
            response,
            (
                f'{reverse("staff-login")}?next='
                f'{reverse("feedback-save-download", kwargs={"receipt_id": self.report.receipt_id})}'
            ),
        )

    def test_staff_can_download_validated_save(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("feedback-save-download", kwargs={"receipt_id": self.report.receipt_id}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(json.loads(response.content)["run_uuid"], "run-001")

    def test_report_without_save_has_no_download(self):
        self.report.has_save_snapshot = False
        self.report.save_snapshot = None
        self.report.save(update_fields=["has_save_snapshot", "save_snapshot"])
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("feedback-save-download", kwargs={"receipt_id": self.report.receipt_id}),
        )

        self.assertEqual(response.status_code, 404)


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
class FeedbackTriageUiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="staff-ui",
            password="correct-horse-battery-staple",
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username="regular-ui",
            password="correct-horse-battery-staple",
        )
        self.report = self.create_report(
            feedback_id="feedback-ui-001",
            message="<script>alert('x')</script> Movement unclear",
            platform="Windows",
            with_save=True,
        )
        self.create_report(
            feedback_id="feedback-ui-002",
            message="Audio volume was too loud",
            platform="Linux",
        )

    def create_report(self, feedback_id, message, platform, with_save=False):
        payload = valid_payload(feedback_id=feedback_id, with_save=with_save)
        payload["message"] = message
        payload["manifest"]["platform"] = platform
        response = self.client.post(
            reverse("game-feedback-v1"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertIn(response.status_code, {200, 201})
        return FeedbackReport.objects.get(feedback_id=feedback_id)

    def test_anonymous_user_cannot_open_triage_inbox(self):
        response = self.client.get(reverse("feedback-triage"))

        self.assertRedirects(
            response,
            f'{reverse("staff-login")}?next={reverse("feedback-triage")}',
        )

    def test_staff_can_filter_report_inbox(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("feedback-triage"),
            {"q": "movement", "platform": "Windows", "save": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "feedback-ui-001")
        self.assertNotContains(response, "feedback-ui-002")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", html=False)

    def test_regular_user_cannot_open_report_detail(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(
            reverse("feedback-report-detail", kwargs={"receipt_id": self.report.receipt_id}),
        )

        self.assertRedirects(
            response,
            (
                f'{reverse("staff-login")}?next='
                f'{reverse("feedback-report-detail", kwargs={"receipt_id": self.report.receipt_id})}'
            ),
        )

    def test_staff_can_toggle_star_from_inbox(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("feedback-report-toggle-star", kwargs={"receipt_id": self.report.receipt_id}),
            {"next": reverse("feedback-triage")},
        )

        self.assertRedirects(response, reverse("feedback-triage"))
        self.report.refresh_from_db()
        self.assertTrue(self.report.is_starred)

    def test_staff_can_update_report_link_issue_and_tags(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("feedback-report-detail", kwargs={"receipt_id": self.report.receipt_id}),
            {
                "is_starred": "on",
                "review_status": FeedbackReport.ReviewStatus.REVIEWED,
                "new_issue_title": "Movement destination choice is unclear",
                "tags": "movement, onboarding, movement",
                "admin_notes": "Clear repro from first report.",
            },
        )

        self.assertRedirects(
            response,
            reverse("feedback-report-detail", kwargs={"receipt_id": self.report.receipt_id}),
        )
        self.report.refresh_from_db()
        self.assertTrue(self.report.is_starred)
        self.assertEqual(self.report.review_status, FeedbackReport.ReviewStatus.REVIEWED)
        self.assertEqual(self.report.matched_issue.title, "Movement destination choice is unclear")
        self.assertEqual(self.report.admin_notes, "Clear repro from first report.")
        self.assertEqual(set(self.report.tags.values_list("slug", flat=True)), {"movement", "onboarding"})
        self.assertEqual(Issue.objects.count(), 1)
        self.assertEqual(Tag.objects.count(), 2)

    def test_report_detail_includes_save_download_link(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("feedback-report-detail", kwargs={"receipt_id": self.report.receipt_id}),
        )

        self.assertContains(
            response,
            reverse("feedback-save-download", kwargs={"receipt_id": self.report.receipt_id}),
        )
