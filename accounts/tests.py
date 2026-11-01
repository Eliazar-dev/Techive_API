import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailOTP, User

A = '/api/auth/'
PW = 'Str0ng-pass-93'


def last_code():
    return re.search(r'code is (\d{6})', mail.outbox[-1].body).group(1)


class RegisterTests(APITestCase):
    def reg(self, **over):
        body = {'name': 'Jane Doe', 'email': 'Jane@Example.com', 'phone': '+254 700 123 456', 'password': PW, 'password2': PW}
        body.update(over)
        return self.client.post(A + 'register/', body, format='json')

    def test_register_then_verify_creates_verified_user_and_sends_welcome(self):
        r = self.reg()
        self.assertEqual(r.status_code, 201)
        u = User.objects.get(email='jane@example.com')
        self.assertFalse(u.email_verified)
        self.assertEqual((u.first_name, u.last_name, u.phone), ('Jane', 'Doe', '+254 700 123 456'))
        self.assertTrue(u.check_password(PW))
        v = self.client.post(A + 'otp/verify/', {'email': 'jane@example.com', 'code': last_code(), 'purpose': 'signup'}, format='json')
        self.assertEqual(v.status_code, 200)
        self.assertEqual(v.data['user']['first_name'], 'Jane')
        u.refresh_from_db()
        self.assertTrue(u.email_verified)
        self.assertTrue(any('Welcome' in m.subject for m in mail.outbox))

    def test_rejects_bad_input(self):
        self.assertEqual(self.reg(password2='different').status_code, 400)
        self.assertEqual(self.reg(password='12345678', password2='12345678').status_code, 400)  # too common / numeric
        self.assertEqual(self.reg(phone='12').status_code, 400)
        self.assertEqual(self.reg(name='J').status_code, 400)
        self.assertEqual(self.reg(email='nope').status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_existing_verified_account_cannot_be_registered_again(self):
        User.objects.create_user('jane@example.com', PW, email_verified=True)
        self.assertEqual(self.reg().status_code, 400)

    def test_unverified_registration_can_be_retried(self):
        self.reg()
        r = self.reg(name='Jane New')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(User.objects.get().first_name, 'Jane')


class LoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('a@example.com', PW, first_name='Ann', email_verified=True)

    def login(self, pw=PW):
        return self.client.post(A + 'login/', {'email': 'A@Example.com', 'password': pw}, format='json')

    def test_password_then_code_gives_tokens(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        r = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': last_code()}, format='json')
        self.assertEqual(r.status_code, 200)
        me = self.client.get(A + 'me/', HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
        self.assertEqual(me.data['first_name'], 'Ann')

    def test_wrong_password_and_unknown_email_look_the_same(self):
        a = self.login('wrong-password')
        b = self.client.post(A + 'login/', {'email': 'nobody@example.com', 'password': PW}, format='json')
        self.assertEqual((a.status_code, b.status_code), (400, 400))
        self.assertEqual(a.data['detail'], b.data['detail'])
        self.assertEqual(len(mail.outbox), 0)

    def test_google_only_account_cannot_use_password_login(self):
        User.objects.create_user('g@example.com', None, email_verified=True)
        r = self.client.post(A + 'login/', {'email': 'g@example.com', 'password': ''}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_remember_me_changes_refresh_lifetime(self):
        self.login()
        code = last_code()
        r = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': code, 'remember': True}, format='json')
        t = RefreshToken(r.data['refresh'])
        self.assertGreater(t['exp'] - t['iat'], timedelta(days=29).total_seconds())
        self.login(); mail.outbox.clear()
        EmailOTP.objects.update(created_at=EmailOTP.objects.first().created_at - timedelta(minutes=5))
        self.login()
        r = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': last_code()}, format='json')
        t = RefreshToken(r.data['refresh'])
        self.assertLessEqual(t['exp'] - t['iat'], timedelta(days=1).total_seconds() + 5)

    def test_code_is_hashed_single_use_and_purpose_bound(self):
        self.login()
        code = last_code()
        self.assertNotIn(code, EmailOTP.objects.get().code_hash)
        wrong_purpose = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': code, 'purpose': 'signup'}, format='json')
        self.assertEqual(wrong_purpose.status_code, 400)
        ok = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': code}, format='json')
        again = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': code}, format='json')
        self.assertEqual((ok.status_code, again.status_code), (200, 400))

    def test_wrong_code_locks_after_five_attempts(self):
        self.login()
        real = last_code()
        wrong = '000000' if real != '000000' else '111111'
        for _ in range(6):
            self.assertEqual(self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': wrong}, format='json').status_code, 400)
        self.assertEqual(self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': real}, format='json').status_code, 400)

    def test_resend_cooldown_and_no_enumeration(self):
        self.login()
        r = self.client.post(A + 'otp/request/', {'email': 'a@example.com', 'purpose': 'login'}, format='json')
        self.assertEqual(r.status_code, 429)
        n = len(mail.outbox)
        r = self.client.post(A + 'otp/request/', {'email': 'ghost@example.com', 'purpose': 'login'}, format='json')
        self.assertEqual((r.status_code, len(mail.outbox)), (200, n))

    @override_settings(ADMIN_EMAILS=['a@example.com'])
    def test_admin_email_is_promoted(self):
        self.login()
        r = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': last_code()}, format='json')
        self.assertTrue(r.data['user']['is_staff'])


class PasswordResetTests(APITestCase):
    def test_forgot_then_reset_then_login_with_new_password(self):
        User.objects.create_user('a@example.com', PW, email_verified=True)
        self.client.post(A + 'password/forgot/', {'email': 'a@example.com'}, format='json')
        code = last_code()
        new = 'An0ther-long-pass'
        bad = self.client.post(A + 'password/reset/', {'email': 'a@example.com', 'code': '999999' if code != '999999' else '111111', 'password': new, 'password2': new}, format='json')
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(A + 'password/reset/', {'email': 'a@example.com', 'code': code, 'password': new, 'password2': new}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(User.objects.get().check_password(new))
        self.assertEqual(self.client.post(A + 'login/', {'email': 'a@example.com', 'password': new}, format='json').status_code, 200)

    def test_forgot_for_unknown_email_is_silent(self):
        r = self.client.post(A + 'password/forgot/', {'email': 'ghost@example.com'}, format='json')
        self.assertEqual((r.status_code, len(mail.outbox)), (200, 0))

    def test_reset_code_cannot_be_used_for_login(self):
        User.objects.create_user('a@example.com', PW, email_verified=True)
        self.client.post(A + 'password/forgot/', {'email': 'a@example.com'}, format='json')
        r = self.client.post(A + 'otp/verify/', {'email': 'a@example.com', 'code': last_code(), 'purpose': 'login'}, format='json')
        self.assertEqual(r.status_code, 400)


@override_settings(GOOGLE_CLIENT_ID='cid')
class GoogleTests(APITestCase):
    INFO = {'email': 'G@Example.com', 'email_verified': True, 'given_name': 'Gina', 'family_name': 'Lee', 'picture': 'https://img.example/g.jpg'}

    def post(self, mode, info=None, exc=None):
        with mock.patch('accounts.views.id_token.verify_oauth2_token', return_value=info or self.INFO, side_effect=exc):
            return self.client.post(A + 'google/', {'credential': 'tok', 'mode': mode}, format='json')

    def test_login_with_unknown_account_returns_no_account(self):
        r = self.post('login')
        self.assertEqual(r.status_code, 404)
        self.assertEqual((r.data['code'], r.data['email'], r.data['picture']), ('no_account', 'g@example.com', 'https://img.example/g.jpg'))
        self.assertFalse(User.objects.exists())

    def test_signup_creates_verified_account_with_photo_and_welcome_email(self):
        r = self.post('signup')
        self.assertEqual(r.status_code, 200)
        u = User.objects.get()
        self.assertEqual((u.email, u.avatar_url, u.email_verified, u.signup_source), ('g@example.com', 'https://img.example/g.jpg', True, 'google'))
        self.assertEqual(r.data['user']['avatar_url'], 'https://img.example/g.jpg')
        self.assertTrue(any('Welcome' in m.subject for m in mail.outbox))

    def test_login_existing_updates_photo(self):
        User.objects.create_user('g@example.com', PW, first_name='G', email_verified=True)
        r = self.post('login')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.get().avatar_url, 'https://img.example/g.jpg')

    @override_settings(ADMIN_EMAILS=['g@example.com'])
    def test_admin_email_promoted_via_google(self):
        self.assertTrue(self.post('signup').data['user']['is_staff'])

    def test_rejected_tokens(self):
        self.assertEqual(self.post('login', info={'email': 'x@y.com', 'email_verified': False}).status_code, 400)
        self.assertEqual(self.post('login', exc=ValueError).status_code, 400)

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_not_configured(self):
        self.assertEqual(self.client.post(A + 'google/', {'credential': 'x'}, format='json').status_code, 503)


@override_settings(MICROSOFT_CLIENT_ID='mid')
class MicrosoftTests(APITestCase):
    def post(self, mode, claims):
        with mock.patch('accounts.views.verify_microsoft', return_value=claims):
            return self.client.post(A + 'microsoft/', {'id_token': 't', 'mode': mode}, format='json')

    def test_signup_creates_unverified_user_and_emails_code(self):
        r = self.post('signup', {'email': 'M@Example.com', 'name': 'Mo Mwangi'})
        self.assertEqual((r.status_code, r.data['need_otp'], r.data['purpose']), (200, True, 'signup'))
        u = User.objects.get()
        self.assertEqual((u.email, u.first_name, u.signup_source, u.email_verified), ('m@example.com', 'Mo', 'microsoft', False))
        v = self.client.post(A + 'otp/verify/', {'email': 'm@example.com', 'code': last_code(), 'purpose': 'signup'}, format='json')
        self.assertEqual(v.status_code, 200)

    def test_login_unknown_account_returns_no_account(self):
        self.assertEqual(self.post('login', {'preferred_username': 'x@example.com'}).status_code, 404)

    def test_login_existing_requires_code(self):
        User.objects.create_user('m@example.com', None, email_verified=True)
        r = self.post('login', {'email': 'm@example.com'})
        self.assertEqual((r.data['need_otp'], r.data['purpose']), (True, 'login'))

    @override_settings(MICROSOFT_CLIENT_ID='')
    def test_not_configured(self):
        self.assertEqual(self.client.post(A + 'microsoft/', {'id_token': 'x'}, format='json').status_code, 503)


class ProfileTests(APITestCase):
    def test_me_requires_auth_and_patch_updates_phone(self):
        self.assertEqual(self.client.get(A + 'me/').status_code, 401)
        u = User.objects.create_user('a@example.com', PW, email_verified=True)
        self.client.force_authenticate(u)
        r = self.client.patch(A + 'me/', {'phone': '0711222333', 'first_name': 'Ann'}, format='json')
        self.assertEqual((r.data['phone'], r.data['first_name']), ('0711222333', 'Ann'))
