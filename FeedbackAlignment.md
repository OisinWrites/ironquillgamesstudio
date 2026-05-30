# Feedback API Alignment Plan

## Goal

Align the Godot feedback uploader with the Django feedback API contract:

`POST https://www.ironquillgamesstudio.com/api/game-feedback/v1/`

The Godot client should produce the clean expected payload. The Django app should remain tolerant of a small number of old-client edge cases so locally queued feedback created before this patch is not unnecessarily rejected.

## Website Contract

Request:

```http
POST /api/game-feedback/v1/
Content-Type: application/json
```

Top-level JSON object must contain:

```json
{
  "manifest": {},
  "message": "",
  "save_snapshot": null
}
```

Expected success response:

```json
{
  "accepted": true,
  "feedback_id": "client-generated-unique-id",
  "receipt_id": "server-generated-uuid"
}
```

HTTP status:

- `201`: accepted new report.
- `200`: duplicate `feedback_id` already received, same receipt returned.
- `400`: invalid payload/schema/content.
- `405`: wrong HTTP method.
- `413`: request or save too large.
- `429`: temporary global rate limit.

## Current Godot State

Relevant files:

- `autoload/feedback_manager.gd`
- `scripts/feedback/feedback_outbox_manager.gd`
- `scripts/feedback/feedback_uploader.gd`
- `scripts/settings/player_settings_data.gd`
- `scripts/app_version.gd`

Current Godot behavior already matches much of the contract:

- Sends JSON with top-level `manifest`, `message`, and `save_snapshot`.
- Uses `Content-Type: application/json`.
- Includes the required manifest fields.
- Uses `feedback_schema_version = 1`.
- Uses `game_version = AppVersion.VERSION`, currently `0.1.0`.
- Uses `build_channel = AppVersion.BUILD_CHANNEL`, currently `demo`.
- Treats both `200` and `201` as upload success.
- Deletes the local package once upload succeeds.

Required corrections remain.

## Required Godot Changes

### 1. Set Production Endpoint

In `scripts/feedback/feedback_uploader.gd`, replace the empty endpoint:

```gdscript
const ENDPOINT: String = ""
```

with:

```gdscript
const ENDPOINT: String = "https://www.ironquillgamesstudio.com/api/game-feedback/v1/"
```

If the project already has a build-channel or environment config convention, use that convention instead of hard-coding, but the demo build must resolve to the production endpoint above.

### 2. Use Explicit UTC `Z` Timestamps

Godot currently uses:

```gdscript
Time.get_datetime_string_from_system(true)
```

This is UTC but may serialize as:

```text
2026-05-30T12:34:56
```

The website expects:

```text
2026-05-30T12:34:56Z
```

Add a small helper for feedback timestamps, for example:

```gdscript
func _utc_timestamp_z() -> String:
    var timestamp: String = Time.get_datetime_string_from_system(true)
    return timestamp if timestamp.ends_with("Z") else timestamp + "Z"
```

Use it for:

- `manifest.created_at_utc`
- `feedback_consent_timestamp_utc`

Files likely affected:

- `scripts/feedback/feedback_outbox_manager.gd`
- `autoload/feedback_manager.gd`

Do not alter unrelated save timestamp behavior unless intentionally scoped.

### 3. Correct No-Save Manifest Filename

Current manifest generation always writes:

```gdscript
"save_snapshot_filename": "save_snapshot.json",
```

Change it to:

```gdscript
"save_snapshot_filename": "save_snapshot.json" if has_snapshot else "",
```

Expected no-save manifest:

```json
{
  "has_save_snapshot": false,
  "save_snapshot_filename": "",
  "save_schema_version": 0
}
```

Keep `save_snapshot` as `null` in the outbound JSON when no save is attached.

### 4. Treat Permanent HTTP Errors Differently From Temporary Failures

Current uploader treats every non-`200/201` response as a retryable failure. That is incorrect for permanent server rejections.

Recommended behavior:

- `200` and `201`: success, delete local package.
- `429`: temporary failure, keep package queued and back off.
- Network failure or `5xx`: temporary failure, keep package queued and back off.
- `400`: permanent invalid payload, quarantine or delete package after logging.
- `405`: permanent client/server route mismatch, quarantine or delete package after logging.
- `413`: permanent too-large package, quarantine or delete package after logging.

Prefer quarantine over immediate deletion if easy:

`user://feedback_outbox_failed/<feedback_id>/`

If quarantine is too much for this patch, deleting permanent failures is acceptable, but log enough information to diagnose the rejection. Do not keep resending known-invalid payloads indefinitely.

Add enough response logging to identify:

- package ID
- HTTP status
- response body if present and reasonably small

### 5. Validate Payload Before Queueing Or Uploading

Add lightweight local validation to catch obvious contract drift:

- Top-level upload payload has exactly `manifest`, `message`, `save_snapshot`.
- `manifest.feedback_schema_version == 1`.
- `manifest.feedback_id` is non-empty.
- `manifest.created_at_utc` is non-empty and ends with `Z`.
- `manifest.game_version` is non-empty.
- `manifest.build_channel` is non-empty.
- `manifest.feedback_policy_version >= 1`.
- If `manifest.has_save_snapshot == false`, `save_snapshot == null` and `save_snapshot_filename == ""`.
- If `manifest.has_save_snapshot == true`, `save_snapshot` is a parsed dictionary and `save_snapshot_filename == "save_snapshot.json"`.

This validation should prevent malformed packages from entering an infinite retry loop.

## Django-Side Compatibility Notes

The clean fix should be made on the Godot side. However, the Django app should tolerate a small number of legacy client edge cases because players may already have queued local feedback packages.

Recommended Django tolerance:

1. Accept UTC datetime strings both with and without trailing `Z`.
   - Normalize missing-`Z` UTC strings internally.

2. Accept old no-save manifests where:

```json
{
  "has_save_snapshot": false,
  "save_snapshot_filename": "save_snapshot.json",
  "save_snapshot": null
}
```

Normalize `save_snapshot_filename` to `""` internally rather than rejecting.

3. Continue treating duplicate `feedback_id` as idempotent success with HTTP `200`.

4. Keep top-level payload shape strict.
   - Require `manifest`, `message`, and `save_snapshot`.
   - Reject missing top-level keys.
   - Reject dangerous or unexpectedly large data.

5. For manifest evolution, prefer schema-versioned validation.
   - `feedback_schema_version = 1` should be strict.
   - Future versions can define additional fields intentionally.

These Django tolerances are compatibility measures, not a replacement for correcting Godot.

## Test Cases

### Godot Client

- Submit feedback with a save snapshot.
- Submit feedback when no save snapshot is available.
- Confirm `created_at_utc` ends in `Z`.
- Confirm `feedback_consent_timestamp_utc` ends in `Z`.
- Confirm no-save manifest uses `save_snapshot_filename = ""`.
- Confirm outbound JSON has exactly `manifest`, `message`, `save_snapshot`.
- Confirm `200` and `201` delete the package.
- Confirm `429` keeps the package queued and backs off.
- Confirm network failure keeps the package queued and backs off.
- Simulate `400`, `405`, and `413`; confirm the package is not retried forever.

### Django Compatibility

- Accept clean Godot payload with save.
- Accept clean Godot payload without save.
- Accept timestamp without trailing `Z` from old queued payloads.
- Accept old no-save filename mismatch and normalize it.
- Reject malformed top-level payloads.
- Reject oversized save snapshots.
- Return `200` for duplicate `feedback_id`.

## Acceptance Criteria

- Godot posts to the correct production endpoint.
- Godot timestamps match the API format.
- Godot no-save manifests accurately report no filename.
- Godot retries only temporary failures.
- Godot does not repeatedly resend permanently invalid packages.
- Django remains tolerant of already-queued old payloads where practical.

