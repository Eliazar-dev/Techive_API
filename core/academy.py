"""Techive Academy: learning, quiz, project, certificate, referrals, Paystack payments, and the staff endpoints for them."""
import json
import logging
import secrets
import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import emails
from . import paystack
from .models import (Certificate, Course, CourseRegistration, Lesson, LessonProgress, LiveSession, Module, Payment,
                     ProjectSubmission, QuizAttempt, QuizQuestion, ReferralProfile, ReferralReward)

log = logging.getLogger(__name__)
CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O/1/I


def course_by(key):
    qs = Course.objects.filter(is_published=True)
    course = qs.filter(pk=key).first() if str(key).isdigit() else qs.filter(slug=key).first()
    if not course:
        raise NotFound('Course not found.')
    return course


class PublicCourse(APIView):
    permission_classes = []

    def get(self, request, slug):
        from .views import CoursePublicSer
        return Response(CoursePublicSer(course_by(slug)).data)


def registration_for(user, course):
    return CourseRegistration.objects.filter(user=user, course=course).first()


def has_access(user, course):
    """Registered, and paid when the course has a fee."""
    reg = registration_for(user, course)
    if not reg or reg.status == CourseRegistration.Status.DROPPED:
        return None
    if course.needs_payment and reg.payment_status != CourseRegistration.Payment.PAID:
        return None
    return reg


def need_access(user, course):
    reg = has_access(user, course)
    if reg is None:
        if registration_for(user, course):
            raise PermissionDenied({'detail': 'Please pay the course fee to continue.', 'code': 'payment_required'})
        raise PermissionDenied({'detail': 'Please register for this course first.', 'code': 'not_registered'})
    return reg


# ---------------------------------------------------------------- referrals
def make_code(user):
    for _ in range(20):
        code = ''.join(secrets.choice(CODE_CHARS) for _ in range(6))
        if not ReferralProfile.objects.filter(code=code).exists():
            return code
    raise RuntimeError('Could not create a referral code')


def referral_profile(user):
    prof = ReferralProfile.objects.filter(user=user).first()
    if prof:
        return prof
    try:
        with transaction.atomic():
            return ReferralProfile.objects.create(user=user, code=make_code(user))
    except IntegrityError:
        return ReferralProfile.objects.get(user=user)


class ReferralView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prof = referral_profile(request.user)
        rewards = list(ReferralReward.objects.filter(referrer=request.user).select_related('referred', 'course'))
        total = lambda st: sum(r.amount for r in rewards if r.status == st)  # noqa: E731
        return Response({
            'code': prof.code,
            'link': f'{settings.ACADEMY_URL.rstrip("/")}/?ref={prof.code}',
            'referred_count': ReferralProfile.objects.filter(referred_by=request.user).count(),
            'earned': total('earned'), 'paid': total('paid'),
            'rewards': [{'id': r.id, 'friend': (r.referred.first_name or r.referred.email.split('@')[0]), 'course': r.course.name,
                         'amount': r.amount, 'status': r.status, 'created_at': r.created_at} for r in rewards],
        })


class ReferralClaim(APIView):
    """POST {code}. Remembers who sent this student. Only once, never yourself, and only before your first payment."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = str(request.data.get('code') or '').strip().upper()
        mine = referral_profile(request.user)
        if mine.referred_by_id:
            return Response({'detail': 'ok'})
        owner = ReferralProfile.objects.filter(code=code).select_related('user').first()
        if not owner or owner.user_id == request.user.id:
            return Response({'detail': 'ok'})  # same answer, nothing to learn from probing codes
        if Payment.objects.filter(user=request.user, status=Payment.Status.SUCCESS).exists():
            return Response({'detail': 'ok'})
        mine.referred_by = owner.user
        mine.save(update_fields=['referred_by'])
        return Response({'detail': 'ok'})


# ---------------------------------------------------------------- payments
def record_success(payment, channel=''):
    """Idempotent: safe to call from the webhook, the return page, or both."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == Payment.Status.SUCCESS:
            return payment
        payment.status = Payment.Status.SUCCESS
        payment.paid_at = timezone.now()
        if channel:
            payment.channel = channel[:30]
        payment.save()
        if payment.purpose == Payment.Purpose.ENROLLMENT:
            reg, _ = CourseRegistration.objects.get_or_create(user=payment.user, course=payment.course)
            reg.payment_status = CourseRegistration.Payment.PAID
            reg.payment_ref = payment.reference
            reg.save(update_fields=['payment_status', 'payment_ref'])
            prof = ReferralProfile.objects.filter(user=payment.user).select_related('referred_by').first()
            reward = payment.course.referral_reward
            if prof and prof.referred_by_id and reward:
                ReferralReward.objects.get_or_create(referred=payment.user, course=payment.course,
                                                     defaults={'referrer': prof.referred_by, 'amount': reward})
    emails.send_payment_receipt(payment)
    return payment


class Checkout(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'pay'

    def post(self, request):
        course = course_by(request.data.get('course'))
        purpose = request.data.get('purpose')
        if purpose not in (Payment.Purpose.ENROLLMENT, Payment.Purpose.CERTIFICATE):
            raise ValidationError({'detail': 'Invalid request.'})
        reg = registration_for(request.user, course)
        if purpose == 'enrollment':
            if not course.needs_payment:
                raise ValidationError({'detail': 'This course is free to join.'})
            if course.status != Course.Status.OPEN and not reg:
                raise ValidationError({'detail': 'This course is not open for registration yet.'})
            if reg and reg.payment_status == CourseRegistration.Payment.PAID:
                raise ValidationError({'detail': 'You have already paid for this course.'})
            amount = course.price
        else:
            need_access(request.user, course)
            if not course.certificate_fee:
                raise ValidationError({'detail': 'The certificate for this course is free.'})
            if Payment.objects.filter(user=request.user, course=course, purpose='certificate', status='success').exists():
                raise ValidationError({'detail': 'You have already paid for this certificate.'})
            amount = course.certificate_fee
        if not paystack.configured():
            raise PermissionDenied({'detail': 'Online payments are not available yet. Please contact us.'})
        if not reg:
            reg = CourseRegistration.objects.create(user=request.user, course=course)
        ref = f'TCH-{uuid.uuid4().hex[:14].upper()}'
        callback = settings.ACADEMY_URL.rstrip('/') + '/pay/return'
        try:
            data = paystack.initialize(request.user.email, amount, ref, callback,
                                       {'course': course.slug, 'purpose': purpose, 'user': request.user.id})
        except paystack.PaystackError as e:
            raise ValidationError({'detail': str(e)})
        Payment.objects.create(user=request.user, course=course, purpose=purpose, amount=amount,
                               currency=settings.PAYSTACK_CURRENCY, reference=ref)
        return Response({'authorization_url': data['authorization_url'], 'reference': ref})


def settle(payment, data):
    """Apply Paystack's verified transaction data to our payment."""
    status = data.get('status')
    if status == 'success':
        if data.get('amount') != payment.amount * 100 or (data.get('currency') or payment.currency) != payment.currency:
            log.error('Payment %s amount/currency mismatch: %s', payment.reference, data)
            return payment
        return record_success(payment, data.get('channel', ''))
    if status in ('failed', 'abandoned', 'reversed') and payment.status == Payment.Status.PENDING:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=['status'])
    return payment


class VerifyPayment(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payment = Payment.objects.filter(reference=request.query_params.get('reference', ''), user=request.user).select_related('course').first()
        if not payment:
            raise NotFound('Payment not found.')
        if payment.status == Payment.Status.PENDING:
            try:
                payment = settle(payment, paystack.verify(payment.reference))
            except paystack.PaystackError:
                pass  # still pending; the webhook may confirm it
        return Response({'status': payment.status, 'purpose': payment.purpose, 'course': payment.course.slug, 'amount': payment.amount})


class PaystackWebhook(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if not paystack.valid_signature(request.body, request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')):
            return Response({'detail': 'Invalid signature.'}, status=400)
        try:
            event = json.loads(request.body.decode())
        except ValueError:
            return Response({'detail': 'Bad request.'}, status=400)
        data = event.get('data') or {}
        if event.get('event') == 'charge.success':
            payment = Payment.objects.filter(reference=data.get('reference', '')).first()
            if payment:
                settle(payment, {**data, 'status': 'success'})
        return Response({'detail': 'ok'})


# ---------------------------------------------------------------- learning
def lesson_json(lesson, done, locked):
    out = {'id': lesson.id, 'title': lesson.title, 'kind': lesson.kind, 'done': lesson.id in done}
    if not locked:
        out.update(video_url=lesson.video_url, body=lesson.body, file_url=lesson.file_url)
    return out


def cert_state(user, course, reg):
    questions = course.questions.count()
    quiz_ok = (not questions) or QuizAttempt.objects.filter(user=user, course=course, passed=True).exists()
    project = ProjectSubmission.objects.filter(user=user, course=course).first()
    project_ok = (not course.project_brief) or bool(project and project.status == 'approved')
    fee_ok = (not course.certificate_fee) or Payment.objects.filter(user=user, course=course, purpose='certificate', status='success').exists()
    cert = Certificate.objects.filter(user=user, course=course).first()
    return {
        'quiz_passed': quiz_ok, 'project_approved': project_ok, 'fee': course.certificate_fee, 'fee_paid': fee_ok,
        'eligible': bool(reg and quiz_ok and project_ok and fee_ok), 'code': cert.code if cert else None,
        'issued_at': cert.issued_at if cert else None,
    }


class Learn(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        course = course_by(slug)
        reg = registration_for(request.user, course)
        if not reg:
            raise PermissionDenied({'detail': 'Please register for this course first.', 'code': 'not_registered'})
        locked = has_access(request.user, course) is None
        done = set(LessonProgress.objects.filter(user=request.user, lesson__module__course=course).values_list('lesson_id', flat=True))
        modules = [{'id': m.id, 'title': m.title, 'lessons': [lesson_json(les, done, locked) for les in m.lessons.all()]}
                   for m in course.modules.prefetch_related('lessons')]
        sessions = [{'id': s.id, 'title': s.title, 'starts_at': s.starts_at, 'notes': s.notes,
                     'meet_url': '' if locked else s.meet_url, 'recording_url': '' if locked else s.recording_url}
                    for s in course.sessions.all()]
        best = QuizAttempt.objects.filter(user=request.user, course=course).order_by('-score').first()
        project = ProjectSubmission.objects.filter(user=request.user, course=course).first()
        nxt = course.next_course if course.next_course and course.next_course.is_published else None
        return Response({
            'course': {'id': course.id, 'name': course.name, 'slug': course.slug, 'description': course.description, 'duration': course.duration,
                       'tutor': course.tutor, 'price': course.price, 'certificate_fee': course.certificate_fee,
                       'project_brief': course.project_brief, 'rules': course.rules, 'payment_plan': course.payment_plan},
            'registration': {'id': reg.id, 'status': reg.status, 'progress': reg.progress, 'progress_note': reg.progress_note, 'payment_status': reg.payment_status},
            'locked': locked, 'modules': modules, 'sessions': sessions,
            'quiz': {'count': course.questions.count(), 'best': best.score if best else None, 'passed': bool(best and best.passed), 'pass_mark': course.quiz_pass_mark},
            'project': ({'status': project.status, 'link': project.link, 'notes': project.notes, 'feedback': project.feedback} if project else None),
            'certificate': cert_state(request.user, course, None if locked else reg),
            'next_course': ({'name': nxt.name, 'slug': nxt.slug, 'price': nxt.price, 'status': nxt.status} if nxt else None),
        })


class CompleteLesson(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        lesson = Lesson.objects.filter(pk=pk, module__course__is_published=True).select_related('module__course').first()
        if not lesson:
            raise NotFound('Lesson not found.')
        course = lesson.module.course
        reg = need_access(request.user, course)
        LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
        total = Lesson.objects.filter(module__course=course).count()
        done = LessonProgress.objects.filter(user=request.user, lesson__module__course=course).count()
        reg.progress = min(100, round(100 * done / total)) if total else reg.progress
        if reg.status == CourseRegistration.Status.REGISTERED:
            reg.status = CourseRegistration.Status.ACTIVE
        reg.save(update_fields=['progress', 'status'])
        return Response({'progress': reg.progress, 'lesson': lesson.id})


class Quiz(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        course = course_by(slug)
        need_access(request.user, course)
        return Response({'pass_mark': course.quiz_pass_mark,
                         'questions': [{'id': q.id, 'text': q.text, 'options': q.options} for q in course.questions.all()]})

    def post(self, request, slug):
        course = course_by(slug)
        need_access(request.user, course)
        qs = list(course.questions.all())
        if not qs:
            raise ValidationError({'detail': 'This course has no quiz.'})
        answers = request.data.get('answers')
        if not isinstance(answers, dict):
            raise ValidationError({'detail': 'Please answer the questions.'})
        correct = sum(1 for q in qs if str(answers.get(str(q.id))) == str(q.correct))
        score = round(100 * correct / len(qs))
        passed = score >= course.quiz_pass_mark
        QuizAttempt.objects.create(user=request.user, course=course, score=score, passed=passed)
        return Response({'score': score, 'passed': passed, 'correct': correct, 'total': len(qs), 'pass_mark': course.quiz_pass_mark})


class SubmitProject(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'academy'

    def post(self, request, slug):
        course = course_by(slug)
        need_access(request.user, course)
        link = str(request.data.get('link') or '').strip()[:500]
        notes = str(request.data.get('notes') or '').strip()[:3000]
        if not link and not notes:
            raise ValidationError({'detail': 'Please add a link to your project or some notes.'})
        if link and not link.lower().startswith(('http://', 'https://')):
            raise ValidationError({'detail': 'The link must start with http:// or https://'})
        sub, created = ProjectSubmission.objects.get_or_create(user=request.user, course=course, defaults={'link': link, 'notes': notes})
        if sub.status == 'approved':
            raise ValidationError({'detail': 'Your project is already approved.'})
        if not created:
            sub.link, sub.notes, sub.status = link, notes, 'pending'
            sub.save()
        try:
            send_mail(f'Project submitted: {course.name}', f'{request.user.email} submitted a project for {course.name}.\n{link}\n{notes}',
                      settings.DEFAULT_FROM_EMAIL, [settings.TEAM_EMAIL], fail_silently=True)
        except Exception:
            log.exception('Team notice failed')
        return Response({'status': sub.status})


def new_cert_code():
    for _ in range(20):
        raw = ''.join(secrets.choice(CODE_CHARS) for _ in range(8))
        code = f'TCH-{raw[:4]}-{raw[4:]}'
        if not Certificate.objects.filter(code=code).exists():
            return code
    raise RuntimeError('Could not create a certificate code')


class IssueCertificate(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        course = course_by(slug)
        reg = need_access(request.user, course)
        state = cert_state(request.user, course, reg)
        if state['code']:
            return Response(state)
        if not state['eligible']:
            raise ValidationError({'detail': 'Finish the quiz, the project and the certificate payment first.', 'state': state})
        name = f'{request.user.first_name} {request.user.last_name}'.strip() or request.user.email
        cert = Certificate.objects.create(user=request.user, course=course, code=new_cert_code(), name=name)
        reg.status, reg.progress = CourseRegistration.Status.COMPLETED, 100
        reg.save(update_fields=['status', 'progress'])
        emails.send_certificate(cert)
        return Response(cert_state(request.user, course, reg), status=201)


class VerifyCertificate(APIView):
    permission_classes = []
    throttle_scope = 'academy'

    def get(self, request, code):
        cert = Certificate.objects.filter(code=code.upper().strip()).select_related('course').first()
        if not cert:
            raise NotFound('No certificate found with this code.')
        return Response({'valid': True, 'name': cert.name, 'course': cert.course.name, 'issued_at': cert.issued_at, 'code': cert.code})


# ---------------------------------------------------------------- staff
class ProjectAdminSer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    name = serializers.SerializerMethodField()
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = ProjectSubmission
        fields = ['id', 'email', 'name', 'course_name', 'link', 'notes', 'status', 'feedback', 'updated_at']
        read_only_fields = ['id', 'email', 'name', 'course_name', 'link', 'notes', 'updated_at']

    def get_name(self, o):
        return f'{o.user.first_name} {o.user.last_name}'.strip()


class AdminProjectList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ProjectAdminSer

    def get_queryset(self):
        qs = ProjectSubmission.objects.select_related('user', 'course')
        st = self.request.query_params.get('status')
        return qs.filter(status=st) if st else qs


class AdminProjectDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ProjectAdminSer
    queryset = ProjectSubmission.objects.select_related('user', 'course')
    http_method_names = ['get', 'patch', 'head', 'options']


class PaymentAdminSer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'email', 'course_name', 'purpose', 'amount', 'currency', 'reference', 'status', 'channel', 'created_at', 'paid_at']


class AdminPaymentList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PaymentAdminSer

    def get_queryset(self):
        qs = Payment.objects.select_related('user', 'course')
        st = self.request.query_params.get('status')
        return qs.filter(status=st) if st else qs


class RewardAdminSer(serializers.ModelSerializer):
    referrer_email = serializers.EmailField(source='referrer.email', read_only=True)
    friend_email = serializers.EmailField(source='referred.email', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = ReferralReward
        fields = ['id', 'referrer_email', 'friend_email', 'course_name', 'amount', 'status', 'created_at', 'paid_at']
        read_only_fields = ['id', 'referrer_email', 'friend_email', 'course_name', 'amount', 'created_at', 'paid_at']


class AdminRewardList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = RewardAdminSer
    queryset = ReferralReward.objects.select_related('referrer', 'referred', 'course')


class AdminRewardDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = RewardAdminSer
    queryset = ReferralReward.objects.select_related('referrer', 'referred', 'course')
    http_method_names = ['get', 'patch', 'head', 'options']

    def perform_update(self, serializer):
        obj = serializer.save()
        obj.paid_at = timezone.now() if obj.status == 'paid' else None
        obj.save(update_fields=['paid_at'])


class SessionSer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = LiveSession
        fields = ['id', 'course', 'course_name', 'title', 'starts_at', 'meet_url', 'notes', 'recording_url']


class AdminSessionList(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SessionSer
    queryset = LiveSession.objects.select_related('course').order_by('-starts_at')


class AdminSessionDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SessionSer
    queryset = LiveSession.objects.select_related('course')


def payment_stats():
    ok = Payment.objects.filter(status='success')
    return {
        'payments_total': ok.count(),
        'revenue_total': ok.aggregate(t=Sum('amount'))['t'] or 0,
        'rewards_owed': ReferralReward.objects.filter(status='earned').aggregate(t=Sum('amount'))['t'] or 0,
        'projects_waiting': ProjectSubmission.objects.filter(status='pending').count(),
    }


# ---------------------------------------------------------------- staff: content management (modules, lessons, questions)
class ModuleSer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ['id', 'course', 'title', 'order']


class LessonSer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ['id', 'module', 'title', 'kind', 'video_url', 'body', 'file_url', 'order']


class QuestionSer(serializers.ModelSerializer):
    class Meta:
        model = QuizQuestion
        fields = ['id', 'course', 'text', 'options', 'correct', 'order']

    def validate_options(self, v):
        if not isinstance(v, list) or not 2 <= len(v) <= 6:
            raise ValidationError('Options must be a list of 2 to 6 items.')
        if not all(isinstance(x, str) and x.strip() for x in v):
            raise ValidationError('Each option must be a non-empty string.')
        return v

    def validate(self, data):
        options = data.get('options', [])
        correct = data.get('correct', 0)
        if isinstance(options, list) and (not isinstance(correct, int) or not 0 <= correct < len(options)):
            raise ValidationError({'correct': '"correct" must be the index of the right option in "options".'})
        return data


class AdminModuleList(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ModuleSer
    pagination_class = None

    def get_queryset(self):
        qs = Module.objects.all()
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminModuleDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ModuleSer
    queryset = Module.objects.all()


class AdminLessonList(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = LessonSer
    pagination_class = None

    def get_queryset(self):
        qs = Lesson.objects.all()
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(module__course_id=course_id)
        return qs


class AdminLessonDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = LessonSer
    queryset = Lesson.objects.all()


class AdminQuestionList(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = QuestionSer
    pagination_class = None

    def get_queryset(self):
        qs = QuizQuestion.objects.all()
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminQuestionDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = QuestionSer
    queryset = QuizQuestion.objects.all()


class QuizAttemptSer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    name = serializers.SerializerMethodField()
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = QuizAttempt
        fields = ['id', 'email', 'name', 'course_name', 'score', 'passed', 'created_at']

    def get_name(self, obj):
        return f'{obj.user.first_name} {obj.user.last_name}'.strip() or obj.user.email


class AdminQuizAttemptList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = QuizAttemptSer
    queryset = QuizAttempt.objects.select_related('user', 'course').order_by('-created_at')

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs
