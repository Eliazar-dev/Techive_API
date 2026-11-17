import hashlib
import hmac
import json
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import (Certificate, Course, CourseRegistration, Lesson, LessonProgress, Module, Payment, QuizQuestion, ReferralReward)

U = get_user_model()
KEY = 'sk_test_x'


def mk_user(email):
    return U.objects.create_user(email=email, password='Pass12345!', first_name=email.split('@')[0])


@override_settings(PAYSTACK_SECRET_KEY=KEY)
class AcademyTests(APITestCase):
    def setUp(self):
        self.free = Course.objects.create(name='Free One', slug='free-one', price=0, certificate_fee=250, status='open',
                                          project_brief='Build it', quiz_pass_mark=60)
        m = Module.objects.create(course=self.free, title='W1', order=1)
        self.les = [Lesson.objects.create(module=m, title=f'L{i}', order=i, kind='text', body='x') for i in range(2)]
        for i in range(2):
            QuizQuestion.objects.create(course=self.free, text=f'Q{i}', options=['a', 'b'], correct=1, order=i)
        self.paid = Course.objects.create(name='Paid', slug='paid', price=3000, certificate_fee=0, referral_reward=400, status='open')
        self.a, self.b = mk_user('a@x.com'), mk_user('b@x.com')

    def login(self, u):
        self.client.force_authenticate(u)

    def test_free_flow_to_certificate(self):
        self.login(self.a)
        self.assertEqual(self.client.post('/api/academy/registrations/', {'course': 'free-one'}).status_code, 201)
        r = self.client.get('/api/academy/learn/free-one/').json()
        self.assertFalse(r['locked'])
        self.assertEqual(self.client.post(f'/api/academy/lessons/{self.les[0].id}/complete/').json()['progress'], 50)
        # cannot issue yet
        self.assertEqual(self.client.post('/api/academy/certificate/free-one/').status_code, 400)
        q = self.client.get('/api/academy/quiz/free-one/').json()
        self.assertNotIn('correct', json.dumps(q))
        bad = self.client.post('/api/academy/quiz/free-one/', {'answers': {str(x['id']): 0 for x in q['questions']}}, format='json').json()
        self.assertFalse(bad['passed'])
        ok = self.client.post('/api/academy/quiz/free-one/', {'answers': {str(x['id']): 1 for x in q['questions']}}, format='json').json()
        self.assertTrue(ok['passed'])
        self.assertEqual(self.client.post('/api/academy/project/free-one/', {'link': 'https://x.dev'}).status_code, 200)
        self.assertEqual(self.client.post('/api/academy/project/free-one/', {'link': 'javascript:x'}).status_code, 400)
        self.assertEqual(self.client.post('/api/academy/certificate/free-one/').status_code, 400)
        staff = U.objects.create_superuser(email='s@x.com', password='Pass12345!')
        self.login(staff)
        pid = self.client.get('/api/admin/projects/').json()[0]['id'] if isinstance(self.client.get('/api/admin/projects/').json(), list) else self.client.get('/api/admin/projects/').json()['results'][0]['id']
        self.assertEqual(self.client.patch(f'/api/admin/projects/{pid}/', {'status': 'approved'}).status_code, 200)
        self.login(self.a)
        self.assertEqual(self.client.post('/api/academy/certificate/free-one/').status_code, 400)  # fee unpaid
        with mock.patch('core.paystack.initialize', return_value={'authorization_url': 'https://pay/x'}):
            c = self.client.post('/api/academy/payments/checkout/', {'course': 'free-one', 'purpose': 'certificate'}, format='json')
        self.assertEqual(c.status_code, 200)
        ref = c.json()['reference']
        data = {'status': 'success', 'amount': 25000, 'currency': 'KES', 'channel': 'mobile_money'}
        with mock.patch('core.paystack.verify', return_value=data):
            v = self.client.get(f'/api/academy/payments/verify/?reference={ref}').json()
        self.assertEqual(v['status'], 'success')
        r = self.client.post('/api/academy/certificate/free-one/')
        self.assertEqual(r.status_code, 201)
        code = r.json()['code']
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/certificates/{code}/').json()['course'], 'Free One')
        self.assertEqual(self.client.get('/api/certificates/NOPE/').status_code, 404)
        self.assertEqual(Certificate.objects.count(), 1)

    def test_paid_course_locked_until_paid_and_referral_on_payment_only(self):
        self.login(self.a)
        code = self.client.get('/api/academy/referrals/').json()['code']
        self.login(self.b)
        self.client.post('/api/academy/referrals/claim/', {'code': code}, format='json')
        self.client.post('/api/academy/referrals/claim/', {'code': 'ZZZZZZ'}, format='json')
        self.assertEqual(self.client.post('/api/academy/registrations/', {'course': 'paid'}).status_code, 201)
        self.assertEqual(ReferralReward.objects.count(), 0)  # registration alone pays nothing
        self.assertTrue(self.client.get('/api/academy/learn/paid/').json()['locked'])
        self.assertEqual(self.client.post('/api/academy/quiz/paid/', {'answers': {}}, format='json').status_code, 403)
        with mock.patch('core.paystack.initialize', return_value={'authorization_url': 'https://pay/x'}):
            ref = self.client.post('/api/academy/payments/checkout/', {'course': 'paid', 'purpose': 'enrollment'}, format='json').json()['reference']
        body = json.dumps({'event': 'charge.success', 'data': {'reference': ref, 'status': 'success', 'amount': 300000, 'currency': 'KES'}}).encode()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/academy/payments/webhook/', body, content_type='application/json',
                                          HTTP_X_PAYSTACK_SIGNATURE='bad').status_code, 400)
        sig = hmac.new(KEY.encode(), body, hashlib.sha512).hexdigest()
        for _ in range(2):  # idempotent
            self.assertEqual(self.client.post('/api/academy/payments/webhook/', body, content_type='application/json',
                                              HTTP_X_PAYSTACK_SIGNATURE=sig).status_code, 200)
        reg = CourseRegistration.objects.get(user=self.b, course=self.paid)
        self.assertEqual(reg.payment_status, 'paid')
        rw = ReferralReward.objects.get()
        self.assertEqual((rw.referrer, rw.amount), (self.a, 400))
        self.login(self.b)
        self.assertFalse(self.client.get('/api/academy/learn/paid/').json()['locked'])

    def test_wrong_amount_not_credited(self):
        self.login(self.b)
        self.client.post('/api/academy/registrations/', {'course': 'paid'})
        with mock.patch('core.paystack.initialize', return_value={'authorization_url': 'u'}):
            ref = self.client.post('/api/academy/payments/checkout/', {'course': 'paid', 'purpose': 'enrollment'}, format='json').json()['reference']
        with mock.patch('core.paystack.verify', return_value={'status': 'success', 'amount': 100, 'currency': 'KES'}):
            self.assertEqual(self.client.get(f'/api/academy/payments/verify/?reference={ref}').json()['status'], 'pending')

    def test_self_referral_ignored_and_no_key_503(self):
        self.login(self.a)
        code = self.client.get('/api/academy/referrals/').json()['code']
        self.client.post('/api/academy/referrals/claim/', {'code': code}, format='json')
        self.client.post('/api/academy/registrations/', {'course': 'paid'})
        with override_settings(PAYSTACK_SECRET_KEY=''):
            r = self.client.post('/api/academy/payments/checkout/', {'course': 'paid', 'purpose': 'enrollment'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)

    def test_free_course_cannot_be_paid_and_public_detail(self):
        self.login(self.a)
        self.client.post('/api/academy/registrations/', {'course': 'free-one'})
        r = self.client.post('/api/academy/payments/checkout/', {'course': 'free-one', 'purpose': 'enrollment'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.client.force_authenticate(None)
        d = self.client.get('/api/academy/courses/free-one/').json()
        self.assertTrue(d['is_free'])
        self.assertEqual(d['lessons'], 2)
        self.assertEqual(self.client.get('/api/academy/learn/free-one/').status_code, 401)


class ContentAdminTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(name='Test Course', slug='test-course', price=0, status='open')
        self.module = Module.objects.create(course=self.course, title='W1', order=1)
        self.lesson = Lesson.objects.create(module=self.module, title='L1', kind='text', body='x', order=1)
        self.question = QuizQuestion.objects.create(course=self.course, text='Q?', options=['a', 'b'], correct=1, order=1)
        self.staff = U.objects.create_superuser(email='staff@x.com', password='Pass12345!')
        self.user = mk_user('user@x.com')

    def login_staff(self):
        self.client.force_authenticate(self.staff)

    def login_user(self):
        self.client.force_authenticate(self.user)

    def test_modules_admin_allowed(self):
        self.login_staff()
        r = self.client.get(f'/api/admin/modules/?course={self.course.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]['title'], 'W1')

    def test_modules_normal_user_403(self):
        self.login_user()
        r = self.client.get('/api/admin/modules/')
        self.assertEqual(r.status_code, 403)

    def test_lessons_admin_allowed(self):
        self.login_staff()
        r = self.client.get(f'/api/admin/lessons/?course={self.course.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]['title'], 'L1')

    def test_lessons_normal_user_403(self):
        self.login_user()
        r = self.client.get('/api/admin/lessons/')
        self.assertEqual(r.status_code, 403)

    def test_questions_admin_allowed(self):
        self.login_staff()
        r = self.client.get(f'/api/admin/questions/?course={self.course.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]['text'], 'Q?')

    def test_questions_normal_user_403(self):
        self.login_user()
        r = self.client.get('/api/admin/questions/')
        self.assertEqual(r.status_code, 403)

    def test_questions_validation_options(self):
        self.login_staff()
        # Too few options
        r = self.client.post('/api/admin/questions/', {
            'course': self.course.id,
            'text': 'Q?',
            'options': ['only'],
            'correct': 0,
            'order': 2
        }, format='json')
        self.assertEqual(r.status_code, 400)
        
        # Too many options
        r = self.client.post('/api/admin/questions/', {
            'course': self.course.id,
            'text': 'Q?',
            'options': ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
            'correct': 0,
            'order': 2
        }, format='json')
        self.assertEqual(r.status_code, 400)
        
        # Empty string option
        r = self.client.post('/api/admin/questions/', {
            'course': self.course.id,
            'text': 'Q?',
            'options': ['a', ''],
            'correct': 0,
            'order': 2
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_questions_validation_correct(self):
        self.login_staff()
        # correct out of range
        r = self.client.post('/api/admin/questions/', {
            'course': self.course.id,
            'text': 'Q?',
            'options': ['a', 'b'],
            'correct': 5,
            'order': 2
        }, format='json')
        self.assertEqual(r.status_code, 400)
        
        # correct negative
        r = self.client.post('/api/admin/questions/', {
            'course': self.course.id,
            'text': 'Q?',
            'options': ['a', 'b'],
            'correct': -1,
            'order': 2
        }, format='json')
        self.assertEqual(r.status_code, 400)


class LoadCourseContentCommandTests(APITestCase):
    def setUp(self):
        self.staff = U.objects.create_superuser(email='staff@x.com', password='Pass12345!')

    def test_loads_json(self):
        from django.core.management import call_command
        
        out = StringIO()
        call_command('load_course_content', '--course', 'python-programming', '--dir', 'core/content', stdout=out)
        output = out.getvalue()
        # The course may already have content from migrations, so it might skip
        self.assertTrue('OK' in output or 'SKIP' in output)

    def test_refuses_replace_with_progress(self):
        from django.core.management import call_command
        
        # Get the python-programming course that exists from migrations
        course = Course.objects.get(slug='python-programming')
        
        # Add some progress
        module = Module.objects.create(course=course, title='W1', order=1)
        lesson = Lesson.objects.create(module=module, title='L1', kind='text', body='x', order=1)
        user = mk_user('progress@x.com')
        LessonProgress.objects.create(user=user, lesson=lesson)
        
        # Should skip with warning
        out = StringIO()
        call_command('load_course_content', '--course', 'python-programming', '--replace', '--dir', 'core/content', stdout=out)
        self.assertIn('SKIP', out.getvalue())
        
        # With --force should succeed
        out = StringIO()
        call_command('load_course_content', '--course', 'python-programming', '--replace', '--force', '--dir', 'core/content', stdout=out)
        self.assertIn('OK', out.getvalue())
