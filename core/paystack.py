"""Tiny Paystack client (hosted checkout). Uses only the standard library.
The student pays on Paystack's page (M-Pesa prompt or card); we then confirm with /transaction/verify and the webhook."""
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings

BASE = 'https://api.paystack.co'


class PaystackError(Exception):
    pass


def configured():
    return bool(settings.PAYSTACK_SECRET_KEY)


def _call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}', 'Content-Type': 'application/json',
                 'User-Agent': 'Techive-Paystack/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        raise PaystackError('Could not reach the payment service.') from e
    if not data.get('status'):
        raise PaystackError(data.get('message') or 'Payment service error.')
    return data['data']


def initialize(email, amount, reference, callback_url, metadata=None):
    """amount = whole KSh (Paystack wants the smallest unit, so x100)."""
    return _call('POST', '/transaction/initialize', {
        'email': email, 'amount': int(amount) * 100, 'currency': settings.PAYSTACK_CURRENCY,
        'reference': reference, 'callback_url': callback_url, 'metadata': metadata or {}})


def verify(reference):
    return _call('GET', f'/transaction/verify/{reference}')


def valid_signature(raw_body, signature):
    if not settings.PAYSTACK_SECRET_KEY or not signature:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
