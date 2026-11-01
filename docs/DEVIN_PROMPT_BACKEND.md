# Prompt for Devin: Techive backend

Copy everything below the line into Devin.

---

You are working in the repository **techive-api** (Django 5, DRF, SimpleJWT, Python 3.11+). It is the backend for the Techive IT Solutions website. The React frontend is a SEPARATE repo (`techive-web`) and talks to this API as described in its `docs/API_CONTRACT.md`. Do not change endpoint paths or response shapes without telling me, because the frontend depends on them.

## Setup
1. Create a venv, `pip install -r requirements.txt`, `cp .env.example .env`.
2. `python manage.py migrate && python manage.py test`. All tests must pass.

## Read first
`README.md`, `config/settings.py`, `config/urls.py`, `accounts/views.py`, `core/views.py`, `core/tests.py`.

## Rules
- Keep it small: no new apps or packages unless essential; no Celery, no Redis, no third-party auth services.
- Never weaken security: OTP codes stay hashed, single-use, rate-limited and attempt-limited; auth responses must not reveal whether an account exists.
- Every behaviour change needs a test in `core/tests.py`.
- Never commit `.env` or secrets.

## Tasks
1. **Email delivery.** Configure real SMTP in `.env` (I will provide host, user, password and the from address). Send a real OTP and a quote notification and confirm they arrive and are not marked as spam (explain SPF/DKIM/DMARC DNS records I need to add for my domain).
2. **Google sign-in.** Put my Google OAuth Web client ID in `.env` as `GOOGLE_CLIENT_ID` and test `POST /api/auth/google/` with a real token from the frontend. The same client ID is used by the frontend. Add my site origin to "Authorized JavaScript origins" in Google Cloud and tell me exactly where to click.
3. **Production deploy on Vercel + Neon.** Follow `docs/DEPLOY_VERCEL_NEON.md` exactly: create the Neon project (pooled connection string), run `python manage.py migrate` against it once, deploy this repo as a Vercel project (framework preset "Other"), and set all environment variables (`DEBUG=False`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `GOOGLE_CLIENT_ID`, `ADMIN_EMAILS`, SMTP). Verify `GET /api/auth/me/` returns 401 JSON and that OTP sign-in works end to end from the deployed frontend. Attach a custom domain for the API (e.g. api.mydomain.com).
4. **Backups & monitoring.** Enable Neon point-in-time restore/backups, and check that errors appear in Vercel's function logs (Python `logging` to stdout is enough).
5. **Small improvements** (after the above works, one PR each):
   - Admin endpoint to export quotes as CSV (`GET /api/admin/quotes/export/`, staff only).
   - Quote status change emails the client when set to `contacted` (optional, behind an env flag).

## Done when
Tests pass, the deployed API works end-to-end with the production frontend (OTP login, Google login, quote submit, academy waitlist, admin dashboard), and a short deployment note is added to `README.md`.
