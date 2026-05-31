import json
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import RequestDataTooBig
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .feedback_validation import FeedbackValidationError, parse_feedback_payload
from .models import FeedbackIngestRejection, FeedbackIngressRateBucket, FeedbackReport, Issue, Tag


def homepage(request):
    return render(request, 'home/index.html')


@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_triage(request):
    reports = FeedbackReport.objects.select_related("matched_issue").prefetch_related("tags")
    reports = _filter_reports(reports, request.GET)
    reports = reports.order_by("-is_starred", "-received_at")[:100]
    issues = Issue.objects.annotate(report_count=Count("reports")).order_by(
        "-is_pinned",
        "-report_count",
        "title",
    )[:12]
    context = {
        "reports": reports,
        "issues": issues,
        "filters": request.GET,
        "stats": {
            "total_reports": FeedbackReport.objects.count(),
            "untriaged_reports": FeedbackReport.objects.filter(
                review_status=FeedbackReport.ReviewStatus.UNTRIAGED,
            ).count(),
            "starred_reports": FeedbackReport.objects.filter(is_starred=True).count(),
            "save_reports": FeedbackReport.objects.filter(has_save_snapshot=True).count(),
            "rejections": FeedbackIngestRejection.objects.count(),
        },
        "review_statuses": FeedbackReport.ReviewStatus.choices,
    }
    return render(request, "home/feedback_triage.html", context)


@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_report_detail(request, receipt_id):
    report = get_object_or_404(
        FeedbackReport.objects.select_related("matched_issue").prefetch_related("tags"),
        receipt_id=receipt_id,
    )
    if request.method == "POST":
        _update_report_from_post(report, request.POST)
        return redirect("feedback-report-detail", receipt_id=report.receipt_id)

    context = {
        "report": report,
        "issues": Issue.objects.order_by("-is_pinned", "title"),
        "review_statuses": FeedbackReport.ReviewStatus.choices,
        "tag_value": ", ".join(tag.name for tag in report.tags.all()),
    }
    return render(request, "home/feedback_report_detail.html", context)


@require_POST
@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_report_toggle_star(request, receipt_id):
    report = get_object_or_404(FeedbackReport, receipt_id=receipt_id)
    report.is_starred = not report.is_starred
    report.save(update_fields=["is_starred"])
    next_url = request.POST.get("next") or "feedback-triage"
    return redirect(next_url)


@require_POST
@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_rejections_clear(request):
    FeedbackIngestRejection.objects.all().delete()
    return redirect("feedback-triage")


@csrf_exempt
@require_POST
def game_feedback_v1(request):
    if not _allow_feedback_request():
        return _reject_feedback("rate_limited", request, status=429, persist=False)
    if request.content_type != "application/json":
        return _reject_feedback("unsupported_content_type", request)

    try:
        raw_body = request.body
    except RequestDataTooBig:
        return _reject_feedback("request_too_large", request, request_size=0, status=413)

    try:
        validated = parse_feedback_payload(raw_body)
    except FeedbackValidationError as error:
        status = 413 if error.reason_code in {"request_too_large", "save_snapshot_too_large"} else 400
        return _reject_feedback(error.reason_code, request, request_size=len(raw_body), status=status)

    feedback_id = validated.report_fields["feedback_id"]
    existing = FeedbackReport.objects.filter(feedback_id=feedback_id).first()
    if existing:
        return _accepted_feedback(existing, status=200)

    try:
        with transaction.atomic():
            report = FeedbackReport.objects.create(**validated.report_fields)
    except IntegrityError:
        report = FeedbackReport.objects.get(feedback_id=feedback_id)
        return _accepted_feedback(report, status=200)
    return _accepted_feedback(report, status=201)


@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_save_download(request, receipt_id):
    report = get_object_or_404(
        FeedbackReport,
        receipt_id=receipt_id,
        has_save_snapshot=True,
        validation_status=FeedbackReport.ValidationStatus.VALIDATED,
    )
    content = json.dumps(report.save_snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="feedback-save-{report.receipt_id}.json"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _allow_feedback_request():
    now = datetime.now(timezone.utc)
    minute = now.strftime("%Y%m%d%H%M")
    with transaction.atomic():
        bucket, _ = FeedbackIngressRateBucket.objects.select_for_update().get_or_create(
            minute=minute,
        )
        if bucket.request_count >= settings.FEEDBACK_GLOBAL_REQUESTS_PER_MINUTE:
            return False
        FeedbackIngressRateBucket.objects.filter(minute=minute).update(
            request_count=F("request_count") + 1,
        )
        if minute.endswith("00"):
            cutoff = (now - timedelta(days=2)).strftime("%Y%m%d%H%M")
            FeedbackIngressRateBucket.objects.filter(minute__lt=cutoff).delete()
    return True


def _filter_reports(reports, filters):
    query = filters.get("q", "").strip()
    if query:
        reports = reports.filter(
            Q(message__icontains=query)
            | Q(normalized_message__icontains=query.lower())
            | Q(feedback_id__icontains=query)
        )

    review_status = filters.get("status", "").strip()
    if review_status:
        reports = reports.filter(review_status=review_status)

    version = filters.get("version", "").strip()
    if version:
        reports = reports.filter(game_version__icontains=version)

    platform = filters.get("platform", "").strip()
    if platform:
        reports = reports.filter(platform__icontains=platform)

    if filters.get("starred") == "1":
        reports = reports.filter(is_starred=True)

    if filters.get("save") == "1":
        reports = reports.filter(has_save_snapshot=True)

    issue_slug = filters.get("issue", "").strip()
    if issue_slug == "none":
        reports = reports.filter(matched_issue__isnull=True)
    elif issue_slug:
        reports = reports.filter(matched_issue__slug=issue_slug)

    return reports


def _update_report_from_post(report, post_data):
    report.review_status = post_data.get("review_status", report.review_status)
    report.admin_notes = post_data.get("admin_notes", "")
    report.is_starred = post_data.get("is_starred") == "on"

    new_issue_title = post_data.get("new_issue_title", "").strip()
    issue_id = post_data.get("matched_issue", "").strip()
    if new_issue_title:
        report.matched_issue = _create_issue(new_issue_title, report)
    elif issue_id:
        report.matched_issue = Issue.objects.filter(id=issue_id).first()
    else:
        report.matched_issue = None

    report.save(update_fields=["review_status", "admin_notes", "is_starred", "matched_issue"])
    report.tags.set(_tags_from_text(post_data.get("tags", "")))


def _create_issue(title, report):
    base_slug = slugify(title)[:180] or "issue"
    slug = base_slug
    counter = 2
    while Issue.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return Issue.objects.create(
        title=title,
        slug=slug,
        first_seen_at=report.received_at,
        last_seen_at=report.received_at,
    )


def _tags_from_text(tag_text):
    tags = []
    seen = set()
    for raw_tag in tag_text.split(","):
        name = raw_tag.strip()
        if not name:
            continue
        slug = slugify(name)[:64]
        if not slug or slug in seen:
            continue
        seen.add(slug)
        tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name[:64]})
        tags.append(tag)
    return tags


def _accepted_feedback(report, status):
    response = JsonResponse(
        {
            "accepted": True,
            "feedback_id": report.feedback_id,
            "receipt_id": str(report.receipt_id),
        },
        status=status,
    )
    response["Cache-Control"] = "no-store"
    return response


def _reject_feedback(reason_code, request, request_size=None, status=400, persist=True):
    if persist:
        FeedbackIngestRejection.objects.create(
            reason_code=reason_code,
            request_size=request_size if request_size is not None else _request_size(request),
        )
    response = JsonResponse({"accepted": False, "error": "invalid_feedback"}, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _request_size(request):
    try:
        return max(0, int(request.META.get("CONTENT_LENGTH", 0)))
    except (TypeError, ValueError):
        return 0
