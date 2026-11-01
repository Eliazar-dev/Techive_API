import re
import uuid

from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from core.models import Course, CourseRegistration, Quote, SiteContent, Visitor, WaitlistEntry

PW = 'Str0ng-pass-93'


def login(client, email='client@example.com'):
    """Real login flow: password, then the emailed code."""
    if not User.objects.filter(email=email).exists():
        User.objects.create_user(email, PW, first_name='Client', email_verified=True)
    client.post('/api/auth/login/', {'email': email, 'password': PW}, format='json')
    code = re.search(r'code is (\d{6})', mail.outbox[-1].body).group(1)
    r = client.post('/api/auth/otp/verify/', {'email': email, 'code': code}, format='json')
    assert r.status_code == 200, r.content
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
    return r.data


class QuoteAndAdminTests(APITestCase):
    def test_quote_requires_sign_in(self):
        self.assertEqual(self.client.post('/api/quotes/', {'message': 'hi'}, format='json').status_code, 401)

    def test_signed_in_user_can_request_quote(self):
        login(self.client)
        r = self.client.post('/api/quotes/', {'service': 'Web Development', 'budget': '50k', 'message': 'Need a site', 'phone': '0700'}, format='json')
        self.assertEqual(r.status_code, 201)
        q = Quote.objects.get()
        self.assertEqual((q.email, q.status), ('client@example.com', 'new'))
        self.assertTrue(any('New quote request' in m.subject for m in mail.outbox))

    def test_blank_name_falls_back_to_profile_name(self):
        login(self.client)
        r = self.client.post('/api/quotes/', {'name': '', 'phone': '', 'service': '', 'budget': '', 'message': 'Hi'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Quote.objects.get().name, 'Client')

    def test_quote_needs_message(self):
        login(self.client)
        self.assertEqual(self.client.post('/api/quotes/', {'service': 'x'}, format='json').status_code, 400)

    def test_waitlist_is_idempotent_and_public(self):
        for _ in range(2):
            self.assertEqual(self.client.post('/api/academy/waitlist/', {'email': 'Z@Example.com', 'course': 'Python'}, format='json').status_code, 201)
        self.assertEqual(WaitlistEntry.objects.count(), 1)

    def test_admin_api_blocked_for_normal_users(self):
        self.assertEqual(self.client.get('/api/admin/stats/').status_code, 401)
        login(self.client)
        for p in ('stats', 'quotes', 'users', 'waitlist', 'courses', 'registrations', 'visitors'):
            self.assertEqual(self.client.get(f'/api/admin/{p}/').status_code, 403, p)
        self.assertEqual(self.client.put('/api/admin/content/home/', {'a': 1}, format='json').status_code, 403)

    @override_settings(ADMIN_EMAILS=['boss@example.com'])
    def test_admin_can_manage_quotes_and_waitlist(self):
        client_user = User.objects.create_user('c@example.com')
        q = Quote.objects.create(user=client_user, name='C', email='c@example.com', message='m', service='SEO')
        w = WaitlistEntry.objects.create(email='w@example.com')
        login(self.client, 'boss@example.com')
        s = self.client.get('/api/admin/stats/').data
        self.assertEqual((s['quotes_total'], s['registrations_total'], s['visitors_total']), (1, 0, 0))
        self.assertEqual(self.client.get('/api/admin/quotes/?status=new').data['count'], 1)
        r = self.client.patch(f'/api/admin/quotes/{q.pk}/', {'status': 'won', 'notes': 'signed', 'message': 'hacked'}, format='json')
        self.assertEqual(r.status_code, 200)
        q.refresh_from_db()
        self.assertEqual((q.status, q.notes, q.message), ('won', 'signed', 'm'))
        self.assertEqual(self.client.patch(f'/api/admin/waitlist/{w.pk}/', {'name': 'Wanjiku'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/admin/waitlist/{w.pk}/').status_code, 204)
        self.assertEqual(self.client.get('/api/admin/users/').status_code, 200)


class AcademyTests(APITestCase):
    def setUp(self):
        self.open = Course.objects.create(name='Prompt Eng', price=15000, duration='4 weeks', mode='online', status='open',
                                          rules='Attend 80% of classes.', payment_plan='50% upfront, 50% mid-course.', order=1)
        self.soon = Course.objects.create(name='Cyber', status='coming_soon', order=2)
        self.hidden = Course.objects.create(name='Secret', is_published=False, order=3)
        SiteContent.objects.create(page='academy', data={'till_number': '123456', 'payment_instructions': 'Pay via Lipa na M-Pesa Till.'})

    def test_seed_migration_created_draft_courses(self):
        self.assertGreaterEqual(Course.objects.filter(track='Building with AI').count(), 5)  # from migration 0003 (+ the 3 made in setUp)

    def test_public_list_hides_unpublished_and_secret_fields(self):
        data = self.client.get('/api/academy/courses/').json()
        names = [c['name'] for c in data]
        self.assertIn('Prompt Eng', names)
        self.assertNotIn('Secret', names)
        self.assertNotIn('rules', data[0])
        self.assertNotIn('payment_plan', data[0])

    def test_registration_requires_sign_in(self):
        self.assertEqual(self.client.post('/api/academy/registrations/', {'course': self.open.id}, format='json').status_code, 401)

    def test_register_emails_student_with_rules_and_till_and_is_idempotent(self):
        login(self.client)
        r = self.client.post('/api/academy/registrations/', {'course': self.open.id, 'phone': '0700111222'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['rules'], 'Attend 80% of classes.')
        self.assertEqual(User.objects.get(email='client@example.com').phone, '0700111222')
        student_mail = [m for m in mail.outbox if m.to == ['client@example.com'] and 'registered' in m.subject][-1]
        self.assertIn('Attend 80%', student_mail.alternatives[0][0])
        self.assertIn('123456', student_mail.alternatives[0][0])
        self.assertEqual(self.client.post('/api/academy/registrations/', {'course': self.open.id}, format='json').status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        mine = self.client.get('/api/academy/registrations/').json()
        self.assertEqual((len(mine), mine[0]['progress']), (1, 0))

    def test_cannot_register_for_coming_soon_or_hidden_course(self):
        login(self.client)
        for c in (self.soon, self.hidden):
            self.assertEqual(self.client.post('/api/academy/registrations/', {'course': c.id}, format='json').status_code, 400)

    def test_academy_info_needs_sign_in(self):
        self.assertEqual(self.client.get('/api/academy/info/').status_code, 401)
        login(self.client)
        self.assertEqual(self.client.get('/api/academy/info/').json()['till_number'], '123456')

    @override_settings(ADMIN_EMAILS=['boss@example.com'])
    def test_staff_manages_courses_and_student_progress(self):
        student = User.objects.create_user('s@example.com', PW, email_verified=True)
        reg = CourseRegistration.objects.create(user=student, course=self.open)
        login(self.client, 'boss@example.com')
        r = self.client.post('/api/admin/courses/', {'name': 'New', 'description': 'd', 'duration': '2 weeks', 'mode': 'hybrid', 'price': 9000}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.json()['id']
        self.assertEqual(self.client.patch(f'/api/admin/courses/{cid}/', {'status': 'coming_soon', 'is_published': False}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(f'/api/admin/courses/{cid}/').status_code, 204)
        self.assertEqual(self.client.get(f'/api/admin/registrations/?course={self.open.id}').json()['count'], 1)
        ok = self.client.patch(f'/api/admin/registrations/{reg.pk}/', {'progress': 40, 'status': 'active', 'progress_note': 'Week 2 done', 'payment_status': 'paid', 'payment_ref': 'QWE123'}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.patch(f'/api/admin/registrations/{reg.pk}/', {'progress': 140}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/admin/registrations/{reg.pk}/', {'course': self.soon.id}, format='json').status_code, 200)
        reg.refresh_from_db()
        self.assertEqual((reg.progress, reg.status, reg.course_id), (40, 'active', self.open.id))  # course cannot be changed


class ContentTests(APITestCase):
    def test_public_content_defaults_to_empty_and_unknown_page_404s_as_400(self):
        self.assertEqual(self.client.get('/api/content/home/').json(), {})
        self.assertEqual(self.client.get('/api/content/nope/').status_code, 400)

    @override_settings(ADMIN_EMAILS=['boss@example.com'])
    def test_staff_saves_content_and_public_sees_it_without_till_number(self):
        login(self.client, 'boss@example.com')
        self.assertEqual(self.client.put('/api/admin/content/about/', {'hero': {'title': 'Hello'}}, format='json').status_code, 200)
        self.assertEqual(self.client.put('/api/admin/content/academy/', {'till_number': '999', 'intro': 'Hi'}, format='json').status_code, 200)
        self.assertEqual(self.client.put('/api/admin/content/home/', ['not', 'an', 'object'], format='json').status_code, 400)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/content/about/').json(), {'hero': {'title': 'Hello'}})
        self.assertEqual(self.client.get('/api/content/academy/').json(), {'intro': 'Hi'})


class VisitorTests(APITestCase):
    def test_track_creates_then_counts_visits(self):
        vid = str(uuid.uuid4())
        self.client.post('/api/track/', {'vid': vid, 'path': '/'}, format='json')
        self.client.post('/api/track/', {'vid': vid, 'path': '/academy'}, format='json')
        v = Visitor.objects.get()
        self.assertEqual((v.visits, v.last_path), (2, '/academy'))

    def test_track_links_signed_in_user_and_rejects_bad_id(self):
        login(self.client)
        vid = str(uuid.uuid4())
        self.client.post('/api/track/', {'vid': vid, 'path': '/'}, format='json')
        self.assertEqual(Visitor.objects.get().user.email, 'client@example.com')
        self.assertEqual(self.client.post('/api/track/', {'vid': 'junk'}, format='json').status_code, 400)

    @override_settings(ADMIN_EMAILS=['boss@example.com'])
    def test_staff_sees_visitors(self):
        Visitor.objects.create(vid=uuid.uuid4(), last_path='/')
        login(self.client, 'boss@example.com')
        self.assertEqual(self.client.get('/api/admin/visitors/').json()['count'], 1)


class StatusTests(APITestCase):
    def test_health_reports_ok_and_db_connected(self):
        r = self.client.get('/api/health/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['status'], r.json()['database']), ('ok', 'connected'))
        self.assertIn('uptime_seconds', r.json())

    def test_status_page_is_html_and_not_cached(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Techive API', r.content)
        self.assertEqual(r['Cache-Control'], 'no-store')
