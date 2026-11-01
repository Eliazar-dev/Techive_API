# Techive API (Django backend)

Django 5 + Django REST Framework + SimpleJWT. Separate repo from the React site (`techive-web`).
No third-party services: OTP codes go out through your own SMTP mailbox; Google sign-in only verifies the Google ID token.

## Run locally
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then edit it
python manage.py migrate
python manage.py runserver                          # http://localhost:8000
python manage.py test                               # 19 tests
```
Open http://localhost:8000/ to see the live status page ("API is running", uptime, database connection). `GET /api/health/` is the JSON behind it, handy for uptime monitors.
In development emails (OTP codes, quote notices) are printed in the terminal, so you can sign in without SMTP.

## Becoming an admin
Put your email in `ADMIN_EMAILS` (comma separated). The next time you sign in with that email (OTP or Google) you are made staff and the **Admin** link appears in the website header (`/admin`).
Optional back-office: `python manage.py createsuperuser` then open `/django-admin/`.

## Structure
```
config/settings.py      all settings, driven by .env
config/urls.py          every endpoint in one place
accounts/               User (email login), EmailOTP, auth views (OTP, Google, me)
core/                   Quote, WaitlistEntry, public + staff API views, tests
```

## Security notes
- OTP codes: 6 digits, stored hashed, expire in 10 min, single use, 5 attempts, 60 s resend cooldown, rate limited.
- Responses never reveal whether an email already has an account.
- Staff endpoints use `IsAdminUser`. Quote `message`/contact fields are read-only for staff; only `status` and `notes` can change.
- Production (`DEBUG=False`) turns on HTTPS redirect, secure cookies and HSTS. Set a long random `SECRET_KEY`.

## Deploy
Vercel + Neon (PostgreSQL): follow `docs/DEPLOY_VERCEL_NEON.md`. Entry point `api/index.py`, config `vercel.json`.
Any other host also works: `pip install -r requirements.txt && python manage.py migrate && gunicorn config.wsgi`.
Endpoint list: see the frontend repo `docs/API_CONTRACT.md`.
