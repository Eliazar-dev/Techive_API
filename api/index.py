# Vercel serverless entry point: exposes the Django WSGI app as `app`.
from config.wsgi import application as app  # noqa: F401
