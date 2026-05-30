# Feedback Website Triage System Plan

Implement the Django website-side receiver, storage, review dashboard, and issue-triage system for Knucklebones feedback reports.

## Goal

Build an admin-only feedback triage system, not a simple inbox.

The Godot game will POST player feedback packages to the website over HTTPS. Each package contains a written message, game/build metadata, consent metadata, and an optional copied save snapshot.

The website must:

- accept and validate hostile internet input safely,
- preserve each valid player report as its own Django model instance,
- store save snapshots privately,
- let admins search, filter, tag, star, and link reports,
- group reports into actionable issues,
- surface frequently reported and fast-growing issues,
- support deterministic similarity suggestions without adding an AI dependency.

## Scope

- Work in the Django website project.
- Inspect the existing project structure, settings, authentication, deployment setup, and database backend before editing.
- Prefer PostgreSQL for production because the triage design benefits from full-text search and trigram similarity.
- Keep the public POST endpoint separate from authenticated admin views.
- Do not expose uploaded save snapshots through public media URLs.
- Do not add AI integrations.
- List all touched files and migrations when finished.

## Expected Godot POST Contract

Create a versioned public endpoint such as:

```text
POST /api/game-feedback/v1/
Content-Type: application/json
```

Expected JSON:

```json
{
  "manifest": {
    "feedback_schema_version": 1,
    "feedback_id": "unique-client-generated-id",
    "created_at_utc": "2026-05-30T12:34:56",
    "game_version": "0.1.0",
    "build_channel": "demo",
    "platform": "Windows",
    "locale": "en_GB",
    "feedback_policy_version": 1,
    "feedback_consent_timestamp_utc": "2026-05-30T12:30:00",
    "has_save_snapshot": true,
    "save_snapshot_filename": "save_snapshot.json",
    "save_schema_version": 1
  },
  "message": "The movement choice was unclear :scream:",
  "save_snapshot": {}
}
```

Reports without saves should use:

```json
{
  "manifest": {
    "has_save_snapshot": false,
    "save_schema_version": 0
  },
  "message": "Feedback from the main menu",
  "save_snapshot": null
}
```

## Response Contract

Return:

```json
{
  "accepted": true,
  "feedback_id": "unique-client-generated-id",
  "receipt_id": "server-generated-id"
}
```

- Return HTTP `201` for a newly accepted report.
- Return HTTP `200` for an already-received duplicate with the same `feedback_id`.
- Make ingestion idempotent. The game may retry after the server accepts a package if the client misses the response.
- Do not return internal validation details unnecessarily.

## Core Models

### 1. `FeedbackReport`

Create one immutable record for each valid player submission.

Suggested fields:

```text
id
feedback_id                 unique
receipt_id                  unique
received_at
created_at_utc
feedback_schema_version
game_version
build_channel
platform
locale
feedback_policy_version
feedback_consent_timestamp_utc
message
normalized_message
save_snapshot
save_schema_version
has_save_snapshot
validation_status
review_status
is_starred
admin_notes
matched_issue               nullable foreign key
```

Requirements:

- Preserve `message` exactly as written.
- Store normalization results separately.
- Escape message output in HTML templates.
- Keep save snapshot storage private.
- Add useful indexes for version, received date, status, star state, and linked issue.

### 2. `Issue`

Create a manually curated actionable issue model.

Suggested fields:

```text
id
title
slug
category
status
severity
summary
internal_notes
is_pinned
first_seen_at
last_seen_at
resolved_in_version
created_at
updated_at
```

Examples:

```text
Movement destination choice is unclear
Bleeder die applies an effect twice
Windows build fails to launch after direct download
Camera transition snaps during movement
```

An issue can link to many `FeedbackReport` records.

### 3. `Tag`

Create reusable tags for cross-cutting topics.

Examples:

```text
combat
movement
onboarding
camera
audio
windows
bleeder
bloody-knuckle
soft-lock
```

Reports and issues may both have tags if useful.

### 4. `IssueRule`

Create editable deterministic classification rules.

Suggested fields:

```text
issue
name
keywords_any
keywords_all
excluded_keywords
applicable_versions
weight
is_active
```

Rules should usually suggest a match for human confirmation rather than silently assigning one.

### 5. Optional `FeedbackIngestRejection`

If useful operationally, store short-lived rejection summaries:

```text
received_at
reason_code
request_size
platform_if_valid
game_version_if_valid
```

Do not retain full malformed payloads by default. Do not build a permanent IP-address archive.

## Ingress Validation

Treat every POST as hostile.

### Request Limits

- Require `Content-Type: application/json`.
- Require HTTPS in production.
- Cap total request body size, for example `700 KiB`.
- Cap message length at `2000` characters.
- Cap save snapshot serialized size at `512 KiB`.
- Reject excessive nesting depth or pathological JSON if practical.
- Rate-limit by IP and global request volume.

### Manifest Validation

- Require known manifest fields and strict types.
- Reject unsupported `feedback_schema_version` values.
- Validate date strings as ISO-like UTC timestamps.
- Apply reasonable maximum lengths to strings.
- Allow only expected build-channel values if practical.
- Do not trust client-supplied filenames.
- Do not accept arbitrary paths.

### Save Validation

- Require `save_snapshot` to be either a JSON object or `null`.
- If `has_save_snapshot` is true, require a JSON object.
- If `has_save_snapshot` is false, require `null`.
- Validate the top-level save `schema_version`.
- For schema version `1`, require the known Godot save keys:

```text
schema_version
created_at_utc
updated_at_utc
run_uuid
save_sequence_number
save_reason
run_manager_snapshot
game_manager_snapshot
player_state_snapshot
board_state_snapshot
map_generation_snapshot
```

- Reject empty `run_uuid`.
- Reject non-positive `save_sequence_number`.
- Require non-empty `run_manager_snapshot` and `player_state_snapshot`.
- Never execute uploaded material.
- Never deserialize uploaded values into arbitrary Python objects.
- Never serve uploaded saves from a path where a web server could interpret them.

### Idempotency

- Put a unique database constraint on `feedback_id`.
- If the same `feedback_id` is submitted again, return the existing receipt with HTTP `200`.
- Do not create duplicate reports.

## Private Save Storage

Choose one of these approaches:

1. Store validated save snapshots in a private `JSONField`.
2. Store validated canonical JSON files in a private storage backend outside publicly served media.

For the first version, a `JSONField` is acceptable because the current client cap is `512 KiB`.

The report detail view should provide an authenticated download endpoint that:

- requires admin/staff permission,
- returns a generated `.json` download,
- sets safe content-disposition headers,
- never exposes an underlying filesystem path.

## Admin-Only Dashboard

Build a dedicated staff-only dashboard. Django admin can remain available for direct model maintenance, but the dashboard should optimize daily triage.

### Dashboard Home

Answer:

```text
What is hurting the current build?
```

Show:

- current-build report count,
- untriaged report count,
- starred report count,
- quarantined/rejected count,
- top issues in the current build,
- fastest-growing issues,
- platform-specific spikes,
- recent reports,
- emoji-token counts.

### Priority Issue List

Show:

```text
Issue | New reports | Total reports | Severity | Latest version | First seen | Last seen | Status | Pin
```

Rank by:

- recent report count,
- growth over a recent time window,
- severity,
- pinned state,
- number of starred linked reports.

Provide filters:

- game version,
- build channel,
- category,
- severity,
- status,
- date range,
- pinned only.

### Report Inbox

Show:

```text
Star | Date | Version | Platform | Message preview | Save | Status | Linked issue | Tags
```

Provide filters:

- untriaged,
- starred,
- quarantined,
- review status,
- version,
- build channel,
- platform,
- locale,
- date range,
- tag,
- linked issue,
- has validated save.

Provide:

- full-text message search,
- bulk tag action,
- bulk link-to-issue action,
- bulk status update,
- star/pin toggle.

### Report Detail

Show:

- full message exactly as written,
- date and version,
- build channel,
- platform and locale,
- validation state,
- policy and consent metadata,
- tags,
- linked issue,
- suggested issues,
- editable admin notes,
- star toggle,
- validated save download button,
- delete/redact action where appropriate.

### Issue Detail

Show:

- issue summary,
- status and severity,
- pin toggle,
- first/last seen dates,
- report counts by version,
- report counts by platform,
- growth over time,
- linked reports,
- starred linked reports,
- editable tags,
- editable issue rules,
- `resolved_in_version`,
- internal notes.

## Deterministic Grouping Without AI

Do not add AI classification initially.

Use a layered approach:

### 1. Message Normalization

Create derived normalization logic:

- lowercase,
- normalize whitespace and punctuation,
- remove common stop words for analysis,
- preserve the original message,
- extract emoji tokens,
- map editable aliases.

Example aliases:

```text
blood die, bloody die -> bloody-knuckle
freeze, frozen, stuck, soft lock, softlock -> soft-lock
square, space, tile -> node
```

Store aliases in data or an editable model rather than hardcoding all vocabulary permanently.

### 2. Rule-Based Suggestions

- Evaluate active `IssueRule` records against normalized text.
- Produce scored issue suggestions.
- Let an admin confirm or reject suggestions.
- Do not silently merge reports solely because a keyword matched.

### 3. PostgreSQL Full-Text Search

Use PostgreSQL-backed Django search:

- `django.contrib.postgres.search.SearchVector`
- `SearchQuery`
- `SearchRank`
- a `GIN` index when report volume justifies it

Use this for inbox search and related-report suggestions.

### 4. PostgreSQL Trigram Similarity

Enable PostgreSQL `pg_trgm` through a Django migration using `TrigramExtension`.

Use trigram similarity for:

- spelling mistakes,
- near-duplicate phrases,
- similar short descriptions,
- candidate related-report suggestions.

Use it as a hint for human review, not as an automatic truth source.

### 5. Phrase And Word Trends

Provide:

- top normalized words,
- top two-word and three-word phrases,
- emoji-token counts,
- trends filtered by version,
- trends filtered by platform,
- trends over recent time windows.

Exclude stop words and allow admins to maintain an ignore list.

## Workflow

A practical daily workflow:

1. Open current-build untriaged reports.
2. Review suggested issue matches.
3. Link reports to existing issues or create a new issue.
4. Star unusually clear or useful reports.
5. Add tags.
6. Download saves only when debugging requires one.
7. Mark issues as investigating, fixed, deferred, or closed.
8. Set `resolved_in_version`.
9. After release, watch whether supposedly fixed issues continue receiving new reports.

## Security And Privacy

- Use HTTPS only in production.
- Keep `DEBUG = False` in production.
- Configure `ALLOWED_HOSTS`.
- Keep secrets out of version control.
- Run:

```text
python manage.py check --deploy
```

- Keep staff dashboard views behind Django authentication and staff checks.
- Do not expose save snapshots publicly.
- Escape user-submitted messages in templates.
- Add retention policies for:
  - raw save snapshots,
  - feedback reports,
  - rejection logs,
  - web-server access logs.
- Provide admin deletion and redaction actions.
- Do not rely on a secret embedded in the Godot executable. Any embedded token can be extracted.
- Use validation, idempotency, HTTPS, and rate limiting as the primary protections.

Useful authoritative references:

- Django file uploads:
  - https://docs.djangoproject.com/en/5.2/ref/files/uploads/
- Django deployment checklist:
  - https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Django PostgreSQL full-text and trigram search:
  - https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/

## Recommended Delivery Phases

### Phase 1: Secure Receiver

- Add app and models.
- Add migrations.
- Add JSON POST endpoint.
- Add strict validation.
- Add idempotency.
- Add private save storage.
- Add authenticated save download.
- Add basic tests.

### Phase 2: Review UI

- Add staff-only report inbox.
- Add report detail view.
- Add filters.
- Add search.
- Add star toggle.
- Add tags.
- Add issue creation and manual linking.

### Phase 3: Issue Dashboard

- Add priority-issue dashboard.
- Add counts by version and platform.
- Add recent-growth ranking.
- Add issue status, severity, pinning, and resolved-version tracking.

### Phase 4: Deterministic Suggestions

- Add normalization.
- Add alias management.
- Add editable issue rules.
- Add PostgreSQL full-text search.
- Add `pg_trgm`.
- Add related-report and suggested-issue hints.

### Phase 5: Trends And Operations

- Add common words and phrase reports.
- Add emoji-token reports.
- Add export tools.
- Add retention cleanup commands.
- Add monitoring and deployment checks.

## Verification

Verify:

- Valid Godot payload creates exactly one `FeedbackReport`.
- Duplicate `feedback_id` returns HTTP `200` without creating a second record.
- New valid report returns HTTP `201`.
- Invalid schema is rejected.
- Oversized message is rejected.
- Oversized request is rejected.
- Invalid save JSON shape is rejected or quarantined according to policy.
- Save download requires staff authentication.
- Save files are not reachable by public URL.
- Message HTML is escaped.
- Dashboard filters work by version, platform, status, tag, issue, and date.
- Star toggle works.
- Issue pinning works.
- Manual report-to-issue linking works.
- Full-text search works.
- Trigram suggestions find near-matches.
- Priority issue ranking favors frequently reported and fast-growing issues.
- `python manage.py check --deploy` is reviewed against production settings.

## Finish Notes

When finished:

- List all touched files and migrations.
- Document environment variables and production settings.
- Document the final POST and response contracts.
- Document rate limits and retention defaults.
- Document whether saves use `JSONField` or private file storage.
- Explain any PostgreSQL-specific setup such as `pg_trgm`.
