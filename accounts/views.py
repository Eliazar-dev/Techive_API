import secrets
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token
from rest_framework import permissions
from rest_framework.exceptions import APIException, Throttled, ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from . import emails
from .models import EmailOTP, User


# ---------------------------------------------------------------- helpers
class Unavailable(APIException):
    status_code = 503
    default_detail = 'This sign-in method is not available.'


def bad(msg):
    return DRFValidationError({'detail': msg})


def user_json(u):
    return {'id': u.id, 'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name,
            'phone': u.phone, 'avatar_url': u.avatar_url, 'is_staff': u.is_staff}


def promote_admin(user):
    if user.email in settings.ADMIN_EMAILS and not user.is_staff:
        user.is_staff = True
        user.save(update_fields=['is_staff'])


def session_for(user, remember=False):
    promote_admin(user)
    refresh = RefreshToken.for_user(user)
    refresh.set_exp(lifetime=timedelta(days=30 if remember else 1))  # "remember me" = 30 days, otherwise 1 day
    return {'access': str(refresh.access_token), 'refresh': str(refresh), 'user': user_json(user)}


def clean_email(value):
    value = (value or '').strip().lower()
    try:
        validate_email(value)
    except ValidationError:
        raise bad('Enter a valid email address.')
    return value


def split_name(full):
    parts = (full or '').strip().split(None, 1)
    return (parts[0] if parts else '')[:150], (parts[1] if len(parts) > 1 else '')[:150]


def issue_otp(email, purpose):
    """Create + email a 6-digit code. Returns False (and sends nothing) if one was sent in the last 60 s."""
    now = timezone.now()
    if EmailOTP.objects.filter(email=email, purpose=purpose, created_at__gte=now - timedelta(seconds=settings.OTP_RESEND_SECONDS)).exists():
        return False
    code = f'{secrets.randbelow(10**6):06d}'
    EmailOTP.objects.filter(email=email, purpose=purpose, used=False).update(used=True)  # invalidate older codes
    EmailOTP.objects.create(email=email, purpose=purpose, code_hash=EmailOTP.digest(email, purpose, code),
                            expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES))
    emails.send_otp(email, code, purpose)
    return True


def check_otp(email, purpose, code):
    """Raises a 400 unless `code` is the current valid code. Consumes it on success."""
    otp = EmailOTP.objects.filter(email=email, purpose=purpose, used=False, expires_at__gt=timezone.now()).order_by('-created_at').first()
    if not otp or otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise bad('Invalid or expired code.')
    if not secrets.compare_digest(otp.code_hash, EmailOTP.digest(email, purpose, str(code or '').strip())):
        otp.attempts += 1
        otp.save(update_fields=['attempts'])
        raise bad('Invalid or expired code.')
    otp.used = True
    otp.save(update_fields=['used'])


def check_password_rules(password, password2, user=None):
    if password != password2:
        raise bad('Passwords do not match.')
    try:
        validate_password(password, user)
    except ValidationError as e:
        raise bad(' '.join(e.messages))


# ---------------------------------------------------------------- email + password
class Register(APIView):
    throttle_scope = 'auth'

    def post(self, request):
        d = request.data
        email = clean_email(d.get('email'))
        name = (d.get('name') or '').strip()
        phone = (d.get('phone') or '').strip()
        if len(name) < 2:
            raise bad('Please enter your name.')
        if len([c for c in phone if c.isdigit()]) < 9:
            raise bad('Please enter a valid phone number.')
        check_password_rules(d.get('password') or '', d.get('password2'))
        user = User.objects.filter(email=email).first()
        if user and user.email_verified:
            raise bad('An account with this email already exists. Please log in.')
        first, last = split_name(name)
        if user is None:
            user = User(email=email)
        user.first_name, user.last_name, user.phone = first, last, phone[:40]
        user.set_password(d['password'])
        user.save()
        issue_otp(email, 'signup')
        return Response({'detail': 'We sent a 6-digit code to your email.', 'email': email, 'purpose': 'signup'}, status=201)


class Login(APIView):
    """Step 1 of login: check email + password, then email a code (step 2 is OTPVerify)."""
    throttle_scope = 'auth'

    def post(self, request):
        email = clean_email(request.data.get('email'))
        user = User.objects.filter(email=email).first()
        password = request.data.get('password') or ''
        if not user or not user.is_active or not user.has_usable_password() or not user.check_password(password):
            raise bad('Incorrect email or password.')
        issue_otp(email, 'login')  # silently skipped if a code was sent in the last minute (still valid)
        return Response({'detail': 'We sent a 6-digit code to your email.', 'email': email, 'purpose': 'login'})


class OTPVerify(APIView):
    throttle_scope = 'otp_verify'

    def post(self, request):
        email = clean_email(request.data.get('email'))
        purpose = request.data.get('purpose') or 'login'
        if purpose not in ('login', 'signup'):
            raise bad('Invalid request.')
        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            raise bad('Invalid or expired code.')
        check_otp(email, purpose, request.data.get('code'))
        if not user.email_verified:  # first successful code = email proven
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            emails.send_welcome(user)
        return Response(session_for(user, bool(request.data.get('remember'))))


class OTPRequest(APIView):
    """Resend a code. Same answer whether or not the email has an account."""
    throttle_scope = 'otp_request'

    def post(self, request):
        email = clean_email(request.data.get('email'))
        purpose = request.data.get('purpose') or 'login'
        if purpose not in ('login', 'signup', 'reset'):
            raise bad('Invalid request.')
        if User.objects.filter(email=email, is_active=True).exists() and not issue_otp(email, purpose):
            raise Throttled(wait=settings.OTP_RESEND_SECONDS, detail='Please wait a minute before requesting another code.')
        return Response({'detail': 'If the email is registered, a code has been sent.'})


class PasswordForgot(APIView):
    throttle_scope = 'otp_request'

    def post(self, request):
        email = clean_email(request.data.get('email'))
        if User.objects.filter(email=email, is_active=True).exists():
            issue_otp(email, 'reset')
        return Response({'detail': 'If the email is registered, a code has been sent.', 'email': email})


class PasswordReset(APIView):
    throttle_scope = 'otp_verify'

    def post(self, request):
        email = clean_email(request.data.get('email'))
        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            raise bad('Invalid or expired code.')
        check_password_rules(request.data.get('password') or '', request.data.get('password2'), user)
        check_otp(email, 'reset', request.data.get('code'))
        user.set_password(request.data['password'])
        user.email_verified = True
        user.save()
        emails.send_password_changed(user)
        return Response({'detail': 'Password updated. You can now log in.'})


# ---------------------------------------------------------------- Google / Microsoft
def no_account(email, name='', picture=''):
    return Response({'detail': 'No account found for this email. Please sign up first.', 'code': 'no_account',
                     'email': email, 'name': name, 'picture': picture}, status=404)


class GoogleAuth(APIView):
    """mode='login' -> 404 no_account if the email is unknown. mode='signup' -> creates the account (already email-verified by Google)."""
    throttle_scope = 'google'

    def post(self, request):
        credential = request.data.get('credential')
        mode = 'signup' if request.data.get('mode') == 'signup' else 'login'
        if not settings.GOOGLE_CLIENT_ID:
            raise Unavailable('Google sign-in is not available.')
        if not credential:
            raise bad('Google sign-in failed.')
        try:
            info = id_token.verify_oauth2_token(credential, g_requests.Request(), settings.GOOGLE_CLIENT_ID)
        except ValueError:
            raise bad('Google sign-in failed.')
        if not info.get('email_verified') or not info.get('email'):
            raise bad('Your Google email is not verified.')
        email = info['email'].lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            if mode == 'login':
                return no_account(email, info.get('name', ''), info.get('picture', ''))
            user = User(email=email, first_name=info.get('given_name', '')[:150], last_name=info.get('family_name', '')[:150],
                        signup_source='google', email_verified=True)
            user.set_unusable_password()
            user.avatar_url = info.get('picture', '')[:500]
            user.save()
            emails.send_welcome(user)
        else:
            if not user.is_active:
                raise bad('This account is disabled.')
            changed = []
            if info.get('picture') and user.avatar_url != info['picture']:
                user.avatar_url = info['picture'][:500]; changed.append('avatar_url')
            if not user.first_name and info.get('given_name'):
                user.first_name, user.last_name = info['given_name'][:150], info.get('family_name', '')[:150]; changed += ['first_name', 'last_name']
            if not user.email_verified:
                user.email_verified = True; changed.append('email_verified')
            if changed:
                user.save(update_fields=changed)
        return Response(session_for(user, True))


_ms_keys = jwt.PyJWKClient('https://login.microsoftonline.com/common/discovery/v2.0/keys')


def verify_microsoft(token):
    try:
        key = _ms_keys.get_signing_key_from_jwt(token).key
        tid = jwt.decode(token, options={'verify_signature': False}).get('tid', '')
        return jwt.decode(token, key, algorithms=['RS256'], audience=settings.MICROSOFT_CLIENT_ID,
                          issuer=f'https://login.microsoftonline.com/{tid}/v2.0')
    except Exception:
        raise bad('Microsoft sign-in failed.')


class MicrosoftAuth(APIView):
    """Microsoft does not guarantee the email is verified, so after the Microsoft check we still email a code (need_otp)."""
    throttle_scope = 'google'

    def post(self, request):
        if not settings.MICROSOFT_CLIENT_ID:
            raise Unavailable('Microsoft sign-in is not available.')
        mode = 'signup' if request.data.get('mode') == 'signup' else 'login'
        claims = verify_microsoft(request.data.get('id_token') or '')
        email = (claims.get('email') or claims.get('preferred_username') or '').strip().lower()
        if '@' not in email:
            raise bad('Microsoft did not return an email address.')
        user = User.objects.filter(email=email).first()
        if user is None:
            if mode == 'login':
                return no_account(email, claims.get('name', ''))
            first, last = split_name(claims.get('name', ''))
            user = User(email=email, first_name=first, last_name=last, signup_source='microsoft')
            user.set_unusable_password()
            user.save()
        elif not user.is_active:
            raise bad('This account is disabled.')
        purpose = 'login' if user.email_verified else 'signup'
        issue_otp(email, purpose)
        return Response({'need_otp': True, 'email': email, 'purpose': purpose, 'detail': 'We sent a 6-digit code to your email.'})


# ---------------------------------------------------------------- profile
class Me(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(user_json(request.user))

    def patch(self, request):
        u = request.user
        for f in ('first_name', 'last_name'):
            if f in request.data:
                setattr(u, f, str(request.data[f])[:150].strip())
        if 'phone' in request.data:
            u.phone = str(request.data['phone'])[:40].strip()
        u.save()
        return Response(user_json(u))
