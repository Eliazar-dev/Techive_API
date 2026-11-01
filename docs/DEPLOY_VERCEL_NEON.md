# Deploy the API on Vercel with a Neon database

## One-time: create the database tables
Vercel does not run migrations, so run them once from your computer against Neon.
1. In Neon: create a project, then copy the **pooled** connection string (host contains `-pooler`).
2. Locally:
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   export DEBUG=False SECRET_KEY=anything-for-this-step DATABASE_URL='postgresql://...-pooler.../neondb?sslmode=require'
   python manage.py migrate
   ```
   Run `python manage.py migrate` again after every release that adds migrations.

## Deploy
1. Push `techive-api` to its own GitHub repo, then in Vercel: **Add New > Project** and import it. Framework preset: **Other**. Leave build/output settings empty.
2. Add these Environment Variables (Production):

| Name | Value |
|---|---|
| `DEBUG` | `False` |
| `SECRET_KEY` | a long random string (`python -c "import secrets;print(secrets.token_urlsafe(60))"`) |
| `DATABASE_URL` | Neon pooled string |
| `ALLOWED_HOSTS` | `.vercel.app,api.yourdomain.com` |
| `CORS_ALLOWED_ORIGINS` | your frontend URL, e.g. `https://techive.co.ke` (no trailing slash) |
| `CSRF_TRUSTED_ORIGINS` | your API URL, e.g. `https://api.yourdomain.com` |
| `GOOGLE_CLIENT_ID` | your Google OAuth web client ID |
| `ADMIN_EMAILS` | your email(s), comma separated |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `TEAM_EMAIL` | your SMTP mailbox (use port 587) |

3. Deploy. Test: `https://<your-api>.vercel.app/api/auth/me/` should answer `401` JSON (that means Django is running).
4. Set the frontend's `VITE_API_URL` to `https://<your-api>.vercel.app/api` and redeploy it.

## Good to know
- Serverless functions are stateless: the database is the only storage. Rate limits use Django's per-process cache, so they are best-effort on Vercel (OTP attempt limits are stored in the database and stay strict).
- The first request after a quiet period can take a second or two (cold start).
- Function time limit is set to 30 s in `vercel.json`.
- Admin back-office at `/django-admin/` needs a superuser: `python manage.py createsuperuser` against the Neon `DATABASE_URL`. Day-to-day, use the React `/admin` page.
