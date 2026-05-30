from django.contrib import admin

from .models import FeedbackIngestRejection, FeedbackReport, Issue, IssueRule, Tag


@admin.register(FeedbackReport)
class FeedbackReportAdmin(admin.ModelAdmin):
    list_display = (
        "feedback_id",
        "received_at",
        "game_version",
        "platform",
        "review_status",
        "has_save_snapshot",
        "is_starred",
    )
    list_filter = (
        "review_status",
        "validation_status",
        "has_save_snapshot",
        "is_starred",
        "build_channel",
        "platform",
    )
    search_fields = ("feedback_id", "message", "game_version")
    readonly_fields = (
        "feedback_id",
        "receipt_id",
        "received_at",
        "created_at_utc",
        "feedback_schema_version",
        "game_version",
        "build_channel",
        "platform",
        "locale",
        "feedback_policy_version",
        "feedback_consent_timestamp_utc",
        "message",
        "normalized_message",
        "save_snapshot",
        "save_schema_version",
        "has_save_snapshot",
    )


admin.site.register(Tag)
admin.site.register(Issue)
admin.site.register(IssueRule)
admin.site.register(FeedbackIngestRejection)
