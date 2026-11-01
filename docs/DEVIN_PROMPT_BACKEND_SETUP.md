# Prompt for Devin: initialize and run the Techive backend

Copy everything below the line into Devin.

---

You are setting up the repository **techive-api** (Django 5.2, Django REST Framework, SimpleJWT, Python 3.11+) so that it runs locally and is ready to deploy. It is the backend for the Techive IT Solutions website. The React frontend is a SEPARATE repo (`techive-web`) and depends on the endpoints in its `docs/API_CONTRACT.md`. Do not rename endpoints or change response shapes. Keep the code small: do not add apps, packages, Celery, Redis or third-party auth services.

## 1. Initialize and run
1. Create a virtual environment and install dependencies:
   `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. `cp .env.example .env` and set at least `DEBUG=True`, a random `SECRET_KEY`, `CORS_ALLOWED_ORIGINS=http://localhost:5173` and `ADMIN_EMAILS=<my email>`. Leave `DATABASE_URL` empty for local SQLite. Leave `EMAIL_BACKEND` as the console backend so OTP codes print in the terminal.
3. `python manage.py migrate`
4. `python manage.py test`: all 19 tests must pass. Fix anything that fails.
5. `python manage.py runserver 8000`

## 2. Verify it is really running
- Open `http://localhost:8000/`. It must show the animated **"API is running"** status page: pulsing green dot, heartbeat line, a ticking uptime counter, "API connection: Connected", response time with a small bar history, server time, a "Refreshing in Ns" countdown and a "Refresh now" button.
- `curl http://localhost:8000/api/health/` must return `{"status":"ok","database":"connected",...}` with HTTP 200.
- Stop the database (or point `DATABASE_URL` at a wrong host) and confirm the page turns amber ("Degraded") and `/api/health/` returns 503. Restore it afterwards.
- Test the full email-OTP flow with curl and note the code printed in the runserver terminal:
  - `POST /api/auth/otp/request/` with `{"email":"me@example.com"}` -> 200 (a second request within 60 s -> 429)
  - `POST /api/auth/otp/verify/` with the code -> 200 with `access`, `refresh`, `user`
  - `GET /api/auth/me/` with `Authorization: Bearer <access>` -> 200
- Sign in with the email in `ADMIN_EMAILS` and confirm `user.is_staff` is `true`, then confirm `GET /api/admin/stats/` returns 200 for that user and 403 for a normal user.
- `POST /api/quotes/` with a bearer token -> 201, and 401 without one.
- Start the frontend (`techive-web`, `VITE_API_URL=http://localhost:8000/api`) and confirm: sign-in with OTP works, the quote form submits, `/admin` shows the quote, and the status page of the API still loads.

## 3. Prepare for production (Vercel + Neon)
Follow `docs/DEPLOY_VERCEL_NEON.md` exactly: create the Neon project, use the **pooled** connection string, run `python manage.py migrate` once against it, deploy the repo to Vercel (framework preset "Other"), set all environment variables from that file, and attach an API domain. After deploying, open the API root URL and confirm the status page shows "API is running" with the database "Connected", and that `GET /api/auth/me/` returns 401 JSON.

## Rules
- Never weaken security: OTP codes stay hashed, single-use, attempt-limited and rate-limited; responses must not reveal whether an account exists; staff endpoints stay behind `IsAdminUser`.
- Never commit `.env` or secrets. Every behaviour change needs a test in `core/tests.py`.
- The status page must keep exposing no secrets, no version numbers and no stack traces.

## Done when
Tests pass (19/19), the server runs, the status page and `/api/health/` behave as described, the OTP/Google/quote/admin flows work with the frontend, and a short summary lists any problems you found and fixed.
