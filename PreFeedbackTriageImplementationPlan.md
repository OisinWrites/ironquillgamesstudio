# Pre-Feedback Triage Implementation Plan

Complete this plan before starting `FeedbackWebsiteTriagePlan.md`. Its purpose is to establish a verified staff workspace, production-safe configuration, and a reliable local development environment.

## Current Foundation

The repository already includes:

- a concealed three-click footer-mark gesture that opens `/studio-access/`;
- a branded Django staff login page with a return-to-site link;
- a branded staff-only `/feedback-triage/` placeholder;
- a logout action;
- Django maintenance admin moved from `/admin/` to `/studio-maintenance/`;
- initial access-control tests.

The concealed gesture is only a discoverability convenience. Server-side authentication remains mandatory.

## Phase 1: Repair The Development Environment

- [ ] Recreate `venv/` locally with an installed Python version supported by Django 5.2.
- [ ] Run `pip install -r requirements.txt`.
- [ ] Confirm `.env` contains local-only values and remains ignored by Git.
- [ ] Run:

```powershell
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Exit criteria: the homepage and staff pages load locally, and the Django test suite passes.

## Phase 2: Complete Staff Authentication

- [ ] Create named Django staff accounts with `python manage.py createsuperuser`.
- [ ] Use unique passwords stored in a password manager.
- [ ] Confirm non-staff accounts cannot enter `/feedback-triage/`.
- [ ] Confirm anonymous requests redirect to `/studio-access/`.
- [ ] Add login throttling using a maintained Django-compatible package or reverse-proxy rule.
- [ ] Document account recovery and staff-account removal.

Do not implement a custom emailed login-key flow initially. Password authentication over HTTPS is sufficient for the first release. Add MFA or emailed one-time codes later only as a second factor.

## Phase 3: Harden Configuration

- [ ] Split development and production expectations clearly in settings.
- [ ] Require a real `SECRET_KEY` when `DEBUG=False`.
- [ ] Set production `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and HTTPS behavior.
- [ ] Confirm production uses PostgreSQL through `DATABASE_URL`.
- [ ] Keep Cloudinary credentials outside version control.
- [ ] Run and review:

```powershell
python manage.py check --deploy
python manage.py collectstatic --noinput
```

## Phase 4: Verify Branded Staff Pages

- [ ] Manually test the three-click footer gesture on desktop and mobile.
- [ ] Verify keyboard users can still reach the login page by direct URL.
- [ ] Verify login errors, logout, return-to-site behavior, and expired sessions.
- [ ] Check that the staff pages visually match the public site.
- [ ] Add automated tests for logout and the relocated maintenance admin.

## Phase 5: Establish Operational Baselines

- [ ] Document deployment steps and required environment variables.
- [ ] Decide where login rate limiting is enforced.
- [ ] Define database backup and restore procedures.
- [ ] Confirm HTTPS is enforced by the deployed platform.
- [ ] Record who can access staff accounts and production secrets.

## Handoff Gate

Start `FeedbackWebsiteTriagePlan.md` only when:

- local tests and deployment checks pass;
- PostgreSQL is available for production;
- staff authentication is verified;
- login throttling and HTTPS are configured;
- deployment and recovery notes exist.

The next implementation phase should then begin with the secure versioned feedback receiver, models, migrations, strict validation, idempotency, and private `JSONField` save storage.
