import json
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import RequestDataTooBig
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .feedback_validation import FeedbackValidationError, parse_feedback_payload
from .models import FeedbackIngestRejection, FeedbackIngressRateBucket, FeedbackReport


def homepage(request):
    return render(request, 'home/index.html')


@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_triage(request):
    return render(request, "home/feedback_triage.html")


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
