import json
import re
import unicodedata
from dataclasses import dataclass

from django.conf import settings
from django.utils.dateparse import parse_datetime


FEEDBACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
EXPECTED_MANIFEST_FIELDS = {
    "feedback_schema_version",
    "feedback_id",
    "created_at_utc",
    "game_version",
    "build_channel",
    "platform",
    "locale",
    "feedback_policy_version",
    "feedback_consent_timestamp_utc",
    "has_save_snapshot",
    "save_snapshot_filename",
    "save_schema_version",
}
REQUIRED_SAVE_FIELDS = {
    "schema_version",
    "created_at_utc",
    "updated_at_utc",
    "run_uuid",
    "save_sequence_number",
    "save_reason",
    "run_manager_snapshot",
    "game_manager_snapshot",
    "player_state_snapshot",
    "board_state_snapshot",
    "map_generation_snapshot",
}


class FeedbackValidationError(Exception):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ValidatedFeedback:
    report_fields: dict


def parse_feedback_payload(raw_body):
    if len(raw_body) > settings.FEEDBACK_MAX_REQUEST_BYTES:
        raise FeedbackValidationError("request_too_large")

    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise FeedbackValidationError("invalid_json")

    _check_json_complexity(payload)
    if not isinstance(payload, dict) or set(payload) != {"manifest", "message", "save_snapshot"}:
        raise FeedbackValidationError("invalid_payload_shape")

    manifest = payload["manifest"]
    if not isinstance(manifest, dict) or set(manifest) != EXPECTED_MANIFEST_FIELDS:
        raise FeedbackValidationError("invalid_manifest_shape")

    fields = {
        "feedback_schema_version": _require_int(manifest, "feedback_schema_version", minimum=1),
        "feedback_id": _require_string(manifest, "feedback_id", maximum=128),
        "created_at_utc": _require_utc_datetime(manifest, "created_at_utc"),
        "game_version": _require_string(manifest, "game_version", maximum=64),
        "build_channel": _require_string(manifest, "build_channel", maximum=32),
        "platform": _require_string(manifest, "platform", maximum=64),
        "locale": _require_string(manifest, "locale", maximum=32),
        "feedback_policy_version": _require_int(manifest, "feedback_policy_version", minimum=1),
        "feedback_consent_timestamp_utc": _require_utc_datetime(
            manifest,
            "feedback_consent_timestamp_utc",
        ),
        "has_save_snapshot": _require_bool(manifest, "has_save_snapshot"),
        "save_schema_version": _require_int(manifest, "save_schema_version", minimum=0),
    }

    if fields["feedback_schema_version"] != 1:
        raise FeedbackValidationError("unsupported_feedback_schema")
    if not FEEDBACK_ID_PATTERN.fullmatch(fields["feedback_id"]):
        raise FeedbackValidationError("invalid_feedback_id")
    save_snapshot_filename = _require_string(
        manifest,
        "save_snapshot_filename",
        maximum=128,
        allow_empty=True,
    )

    message = payload["message"]
    if not isinstance(message, str) or not message.strip():
        raise FeedbackValidationError("invalid_message")
    if len(message) > settings.FEEDBACK_MAX_MESSAGE_LENGTH:
        raise FeedbackValidationError("message_too_large")

    save_snapshot = payload["save_snapshot"]
    if fields["has_save_snapshot"]:
        _validate_save_snapshot(save_snapshot, fields["save_schema_version"])
    elif save_snapshot is not None or fields["save_schema_version"] != 0:
        raise FeedbackValidationError("unexpected_save_snapshot")
    elif save_snapshot_filename not in {"", "save_snapshot.json"}:
        raise FeedbackValidationError("unexpected_save_snapshot_filename")

    fields.update(
        message=message,
        normalized_message=normalize_message(message),
        save_snapshot=save_snapshot,
    )
    return ValidatedFeedback(report_fields=fields)


def normalize_message(message):
    normalized = unicodedata.normalize("NFKC", message).lower()
    normalized = re.sub(r"[^\w\s:]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _validate_save_snapshot(snapshot, manifest_schema_version):
    if not isinstance(snapshot, dict):
        raise FeedbackValidationError("invalid_save_snapshot")
    if manifest_schema_version != 1 or snapshot.get("schema_version") != 1:
        raise FeedbackValidationError("unsupported_save_schema")
    if not REQUIRED_SAVE_FIELDS.issubset(snapshot):
        raise FeedbackValidationError("invalid_save_shape")
    _require_utc_datetime(snapshot, "created_at_utc")
    _require_utc_datetime(snapshot, "updated_at_utc")
    if not isinstance(snapshot["run_uuid"], str) or not snapshot["run_uuid"].strip():
        raise FeedbackValidationError("invalid_run_uuid")
    if not isinstance(snapshot["save_reason"], str) or not snapshot["save_reason"].strip():
        raise FeedbackValidationError("invalid_save_reason")
    if (
        isinstance(snapshot["save_sequence_number"], bool)
        or not isinstance(snapshot["save_sequence_number"], int)
        or snapshot["save_sequence_number"] <= 0
    ):
        raise FeedbackValidationError("invalid_save_sequence")
    for key in ("run_manager_snapshot", "player_state_snapshot"):
        if not isinstance(snapshot[key], dict) or not snapshot[key]:
            raise FeedbackValidationError("invalid_save_shape")
    for key in (
        "game_manager_snapshot",
        "board_state_snapshot",
        "map_generation_snapshot",
    ):
        if not isinstance(snapshot[key], dict):
            raise FeedbackValidationError("invalid_save_shape")
    serialized = json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(serialized) > settings.FEEDBACK_MAX_SAVE_BYTES:
        raise FeedbackValidationError("save_snapshot_too_large")


def _require_string(source, key, maximum, allow_empty=False):
    value = source.get(key)
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise FeedbackValidationError(f"invalid_{key}")
    return value


def _require_int(source, key, minimum):
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FeedbackValidationError(f"invalid_{key}")
    return value


def _require_bool(source, key):
    value = source.get(key)
    if not isinstance(value, bool):
        raise FeedbackValidationError(f"invalid_{key}")
    return value


def _require_utc_datetime(source, key):
    value = _require_string(source, key, maximum=40)
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
        value = f"{value}+00:00"
    parsed = parse_datetime(value)
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise FeedbackValidationError(f"invalid_{key}")
    return parsed


def _check_json_complexity(value, depth=0, state=None):
    if state is None:
        state = {"nodes": 0}
    state["nodes"] += 1
    if depth > 32 or state["nodes"] > 20000:
        raise FeedbackValidationError("json_too_complex")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise FeedbackValidationError("invalid_json")
            _check_json_complexity(child, depth + 1, state)
    elif isinstance(value, list):
        for child in value:
            _check_json_complexity(child, depth + 1, state)
