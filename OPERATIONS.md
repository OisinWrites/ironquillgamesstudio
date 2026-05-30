# Website Operations

This repository deploys the live Iron Quill Games Studio Django website to Heroku. Treat deployment commands, Heroku configuration changes, Cloudinary uploads, and production database commands as production operations.

## Required Environment Variables

Configure these as Heroku config vars. Keep real values out of Git.

| Variable | Production requirement |
| --- | --- |
| `SECRET_KEY` | Long random secret. Required when `DEBUG=False`. |
| `DEBUG` | Set to `False`. |
| `ALLOWED_HOSTS` | Comma-separated public hostnames, without schemes. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins, including schemes. |
| `DATABASE_URL` | Heroku PostgreSQL connection URL. Required when `DEBUG=False`. |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary account name. |
| `CLOUDINARY_API_KEY` | Cloudinary API key. |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret. |

Local development uses `.env`, SQLite, and `DEBUG=True`. The `.env` file is ignored by Git.

## Deployment

Before deploying:

```powershell
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py test
venv\Scripts\python.exe manage.py collectstatic --noinput
```

Review the Heroku config vars, deploy through the project's normal Heroku Git workflow, then run:

```powershell
heroku run python manage.py migrate --app <app-name>
heroku run python manage.py check --deploy --app <app-name>
```

Verify the homepage, `/studio-access/`, `/feedback-triage/`, and `/studio-maintenance/` over HTTPS after deployment.

## Staff Accounts

Create one named account per staff member:

```powershell
heroku run python manage.py createsuperuser --app <app-name>
```

Store unique passwords in the studio password manager. Do not share accounts.

For password recovery, an authorized operator should set a new password:

```powershell
heroku run python manage.py changepassword <username> --app <app-name>
```

To remove access, set `is_active=False` and `is_staff=False` in `/studio-maintenance/`. Delete an account only when its audit history is no longer needed.

## Login Throttling

`django-axes` enforces login throttling in Django. Five failed authentication attempts lock a username for one hour. This covers both `/studio-access/` and the relocated Django maintenance admin.

Lockouts are keyed by username because Heroku documents that its forwarded headers are not trustworthy for security decisions. This prevents distributed password guessing against a known staff account, but it also means repeated failures can temporarily lock that account. An authorized operator can clear a lockout:

```powershell
heroku run python manage.py axes_reset_username <username> --app <app-name>
```

## HTTPS

With `DEBUG=False`, Django redirects HTTP requests to HTTPS, trusts Heroku's `X-Forwarded-Proto` header for protocol detection, uses secure session and CSRF cookies, and sends an HSTS header. Confirm HTTPS redirects after every deployment.

## Game Feedback Receiver

The versioned receiver accepts:

```text
POST /api/game-feedback/v1/
Content-Type: application/json
```

New valid reports return HTTP `201`. A retried `feedback_id` returns the existing receipt with HTTP `200`. Reports are idempotent because `feedback_id` is unique.

The receiver rejects bodies over `700 KiB`, messages over `2000` characters, save snapshots over `512 KiB`, excessive JSON nesting, unsupported schemas, and invalid save shapes. It stores short rejection summaries without retaining malformed payloads.

Validated save snapshots are stored privately in PostgreSQL `JSONField` data. They are never written under `MEDIA_URL`. Staff downloads are generated through an authenticated endpoint.

The application enforces a shared global receiver limit of `120` requests per minute using PostgreSQL rate buckets. Heroku does not provide a trustworthy client-IP header for application security decisions. Add an edge rate limit if a trusted proxy or web application firewall is introduced later.

Retention defaults:

- preserve accepted feedback reports until a reviewed studio retention policy replaces this default;
- preserve validated save snapshots with their reports until the same review;
- retain short rejection summaries temporarily and prune them operationally once the dashboard phase adds a cleanup command;
- retain rate-limit buckets for approximately two days.

## Database Backup And Restore

Use Heroku PostgreSQL backups before schema changes:

```powershell
heroku pg:backups:capture --app <app-name>
heroku pg:backups --app <app-name>
```

Restore only during an approved maintenance window. Capture a fresh backup first, identify the exact backup ID, and follow the current Heroku PostgreSQL restore procedure for the attached database. A restore replaces production data and requires explicit operator approval.

## Access Record

Maintain a private studio record outside this repository listing:

- staff-account owners;
- Heroku collaborators;
- Cloudinary credential holders;
- password-manager vault members;
- the date access was granted or removed.
