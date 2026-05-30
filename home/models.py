import uuid

from django.db import models
from django.utils import timezone


class Tag(models.Model):
    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=64, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Issue(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        FIXED = "fixed", "Fixed"
        DEFERRED = "deferred", "Deferred"
        CLOSED = "closed", "Closed"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    category = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MEDIUM)
    summary = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    is_pinned = models.BooleanField(default=False)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    resolved_in_version = models.CharField(max_length=64, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="issues")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-updated_at"]

    def __str__(self):
        return self.title


class FeedbackReport(models.Model):
    class ValidationStatus(models.TextChoices):
        VALIDATED = "validated", "Validated"
        QUARANTINED = "quarantined", "Quarantined"

    class ReviewStatus(models.TextChoices):
        UNTRIAGED = "untriaged", "Untriaged"
        REVIEWED = "reviewed", "Reviewed"
        ACTIONED = "actioned", "Actioned"
        ARCHIVED = "archived", "Archived"

    feedback_id = models.CharField(max_length=128, unique=True)
    receipt_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_at_utc = models.DateTimeField()
    feedback_schema_version = models.PositiveSmallIntegerField()
    game_version = models.CharField(max_length=64, db_index=True)
    build_channel = models.CharField(max_length=32, db_index=True)
    platform = models.CharField(max_length=64, db_index=True)
    locale = models.CharField(max_length=32)
    feedback_policy_version = models.PositiveSmallIntegerField()
    feedback_consent_timestamp_utc = models.DateTimeField()
    message = models.TextField()
    normalized_message = models.TextField()
    save_snapshot = models.JSONField(null=True, blank=True)
    save_schema_version = models.PositiveSmallIntegerField(default=0)
    has_save_snapshot = models.BooleanField(default=False)
    validation_status = models.CharField(
        max_length=16,
        choices=ValidationStatus.choices,
        default=ValidationStatus.VALIDATED,
        db_index=True,
    )
    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.UNTRIAGED,
        db_index=True,
    )
    is_starred = models.BooleanField(default=False, db_index=True)
    admin_notes = models.TextField(blank=True)
    matched_issue = models.ForeignKey(
        Issue,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="reports")

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.feedback_id} ({self.game_version})"


class IssueRule(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=120)
    keywords_any = models.JSONField(default=list, blank=True)
    keywords_all = models.JSONField(default=list, blank=True)
    excluded_keywords = models.JSONField(default=list, blank=True)
    applicable_versions = models.JSONField(default=list, blank=True)
    weight = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["issue", "name"]

    def __str__(self):
        return self.name


class FeedbackIngestRejection(models.Model):
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    reason_code = models.CharField(max_length=64, db_index=True)
    request_size = models.PositiveIntegerField(default=0)
    platform_if_valid = models.CharField(max_length=64, blank=True)
    game_version_if_valid = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return self.reason_code


class FeedbackIngressRateBucket(models.Model):
    minute = models.CharField(max_length=12, primary_key=True)
    request_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.minute
