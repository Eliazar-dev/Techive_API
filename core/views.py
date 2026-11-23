import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts import emails
from .models import Course, CourseRegistration, Payment, Quote, SiteContent, Visitor, WaitlistEntry
from . import csv_utils

log = logging.getLogger(__name__)


# ---------- serializers ----------
class QuoteIn(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = ['name', 'phone', 'service', 'budget', 'message']
        extra_kwargs = {'name': {'required': False, 'allow_blank': True}}  # blank -> falls back to profile name


class QuoteAdminSer(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = ['id', 'name', 'email', 'phone', 'service', 'budget', 'message', 'status', 'notes', 'created_at']
        read_only_fields = ['id', 'name', 'email', 'phone', 'service', 'budget', 'message', 'created_at']


class UserAdminSer(serializers.ModelSerializer):
    quotes = serializers.IntegerField(source='quote_count', read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'is_staff', 'is_active', 'date_joined', 'last_login', 'quotes']


class WaitlistSer(serializers.ModelSerializer):
    class Meta:
        model = WaitlistEntry
        fields = ['id', 'email', 'name', 'course', 'created_at']


# ---------- public / signed-in ----------
class QuoteCreate(generics.CreateAPIView):
    """Quotes require a signed-in (OTP or Google) user."""
    permission_classes = [IsAuthenticated]
    serializer_class = QuoteIn
    throttle_scope = 'quote'

    def perform_create(self, serializer):
        u = self.request.user
        name = serializer.validated_data.get('name') or f'{u.first_name} {u.last_name}'.strip() or u.email.split('@')[0]
        q = serializer.save(user=u, email=u.email, name=name)
        try:
            send_mail(
                f'New quote request: {q.service or "General"} - {q.name}',
                f'Name: {q.name}\nEmail: {q.email}\nPhone: {q.phone}\nService: {q.service}\nBudget: {q.budget}\n\n{q.message}',
                settings.DEFAULT_FROM_EMAIL, [settings.TEAM_EMAIL], fail_silently=False)
            send_mail(
                'We received your quote request',
                f'Hi {q.name},\n\nThanks for contacting Techive IT Solutions. We received your request and will reply within one business day.\n\nTechive IT Solutions',
                settings.DEFAULT_FROM_EMAIL, [q.email], fail_silently=False)
        except Exception:
            log.exception('Quote email failed (quote %s saved)', q.pk)

    def create(self, request, *args, **kwargs):
        super().create(request, *args, **kwargs)
        return Response({'detail': 'ok'}, status=201)


class WaitlistCreate(APIView):
    permission_classes = []
    throttle_scope = 'waitlist'

    def post(self, request):
        s = WaitlistSer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        WaitlistEntry.objects.get_or_create(
            email=d['email'].lower(), defaults={'name': d.get('name', ''), 'course': d.get('course', '')})
        return Response({'detail': 'ok'}, status=201)  # same answer whether new or existing


# ---------- staff-only (React /admin) ----------
from .academy import payment_stats  # noqa: E402


class AdminStats(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        week = timezone.now() - timedelta(days=7)
        return Response({
            'quotes_total': Quote.objects.count(),
            'quotes_new': Quote.objects.filter(status='new').count(),
            'quotes_week': Quote.objects.filter(created_at__gte=week).count(),
            'users_total': User.objects.count(),
            'waitlist_total': WaitlistEntry.objects.count(),
            'registrations_total': CourseRegistration.objects.count(),
            'visitors_total': Visitor.objects.count(),
            **payment_stats(),
            'by_service': list(Quote.objects.exclude(service='').values('service').annotate(n=Count('id')).order_by('-n')[:8]),
            'by_status': {r['status']: r['n'] for r in Quote.objects.values('status').annotate(n=Count('id'))},
        })


class AdminQuoteList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = QuoteAdminSer

    def get_queryset(self):
        qs = Quote.objects.all()
        st = self.request.query_params.get('status')
        return qs.filter(status=st) if st else qs


class AdminQuoteDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = QuoteAdminSer
    queryset = Quote.objects.all()


class AdminUserList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserAdminSer
    queryset = User.objects.annotate(quote_count=Count('quotes')).order_by('-date_joined')


class AdminWaitlistList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = WaitlistSer
    queryset = WaitlistEntry.objects.all()


class AdminWaitlistDetail(generics.RetrieveUpdateDestroyAPIView):
    """Staff can fix a name/course or remove an entry."""
    permission_classes = [IsAdminUser]
    serializer_class = WaitlistSer
    queryset = WaitlistEntry.objects.all()
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']


# ======================================================================
# Academy: courses, registrations
# ======================================================================
class CourseSer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'name', 'track', 'description', 'duration', 'mode', 'price', 'tutor', 'rules', 'payment_plan', 'status', 'is_published', 'order',
                  'slug', 'certificate_fee', 'referral_reward', 'quiz_pass_mark', 'project_title', 'project_brief', 'project_requirements', 'next_course']
        extra_kwargs = {'slug': {'required': False, 'allow_null': True, 'allow_blank': True}}

    def validate_slug(self, v):
        return v or None


class CoursePublicSer(serializers.ModelSerializer):
    """Rules and payment plan are NOT in the public list: they are only revealed after registering."""
    class Meta:
        model = Course
        fields = ['id', 'name', 'slug', 'track', 'description', 'duration', 'mode', 'price', 'certificate_fee',
                  'referral_reward', 'tutor', 'status', 'is_free', 'lessons', 'next_course_slug']

    is_free = serializers.SerializerMethodField()
    lessons = serializers.SerializerMethodField()
    next_course_slug = serializers.SlugRelatedField(source='next_course', slug_field='slug', read_only=True)

    def get_is_free(self, c):
        return not c.needs_payment and c.price is not None

    def get_lessons(self, c):
        return sum(m.lessons.count() for m in c.modules.all())


class RegistrationSer(serializers.ModelSerializer):
    course = CoursePublicSer(read_only=True)
    rules = serializers.CharField(source='course.rules', read_only=True)
    payment_plan = serializers.CharField(source='course.payment_plan', read_only=True)

    class Meta:
        model = CourseRegistration
        fields = ['id', 'course', 'status', 'progress', 'progress_note', 'payment_status', 'created_at', 'rules', 'payment_plan']


class RegistrationAdminSer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    name = serializers.SerializerMethodField()
    phone = serializers.CharField(source='user.phone', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = CourseRegistration
        fields = ['id', 'email', 'name', 'phone', 'course', 'course_name', 'status', 'progress', 'progress_note', 'payment_status', 'payment_ref', 'created_at']
        read_only_fields = ['id', 'email', 'name', 'phone', 'course', 'course_name', 'created_at']

    def get_name(self, obj):
        return f'{obj.user.first_name} {obj.user.last_name}'.strip()

    def validate_progress(self, v):
        if not 0 <= v <= 100:
            raise ValidationError('Progress must be between 0 and 100.')
        return v


def academy_settings():
    row = SiteContent.objects.filter(page='academy').first()
    return (row.data if row else {}) or {}


class PublicCourseList(generics.ListAPIView):
    permission_classes = []
    serializer_class = CoursePublicSer
    pagination_class = None
    queryset = Course.objects.filter(is_published=True)


class MyRegistrations(generics.ListCreateAPIView):
    """Signed-in students: GET their registrations (with progress), POST {course} to register."""
    permission_classes = [IsAuthenticated]
    serializer_class = RegistrationSer
    pagination_class = None
    throttle_scope = 'academy'

    def get_queryset(self):
        return CourseRegistration.objects.filter(user=self.request.user).select_related('course')

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []

    def create(self, request, *args, **kwargs):
        key = str(request.data.get('course') or '')
        pub = Course.objects.filter(is_published=True)
        course = pub.filter(pk=key).first() if key.isdigit() else pub.filter(slug=key).first()
        if not course:
            raise ValidationError({'detail': 'Course not found.'})
        if course.status != Course.Status.OPEN:
            raise ValidationError({'detail': 'This course is not open for registration yet. Join the waitlist instead.'})
        phone = (request.data.get('phone') or '').strip()
        if phone and not request.user.phone:
            request.user.phone = phone[:40]
            request.user.save(update_fields=['phone'])
        reg, created = CourseRegistration.objects.get_or_create(user=request.user, course=course)
        if created:
            cfg = academy_settings()
            emails.send_course_registration(reg, cfg.get('till_number', ''), cfg.get('payment_instructions', ''))
            try:
                send_mail(f'New course registration: {course.name}',
                          f'{request.user.email} ({request.user.first_name} {request.user.last_name}, {request.user.phone}) registered for {course.name}.',
                          settings.DEFAULT_FROM_EMAIL, [settings.TEAM_EMAIL], fail_silently=True)
            except Exception:
                log.exception('Team notice failed')
        return Response(RegistrationSer(reg).data, status=201 if created else 200)


# ---- staff: courses / students ----
class AdminCourseList(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CourseSer
    queryset = Course.objects.all()


class AdminCourseDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CourseSer
    queryset = Course.objects.all()


class AdminRegistrationList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = RegistrationAdminSer

    def get_queryset(self):
        qs = CourseRegistration.objects.select_related('user', 'course')
        p = self.request.query_params
        if p.get('course'):
            qs = qs.filter(course_id=p['course'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('payment_status'):
            qs = qs.filter(payment_status=p['payment_status'])
        return qs


class AdminRegistrationDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = RegistrationAdminSer
    queryset = CourseRegistration.objects.select_related('user', 'course')
    http_method_names = ['get', 'patch', 'head', 'options']


# ======================================================================
# Editable page content (CMS) + cookie-consented visitors
# ======================================================================
CONTENT_PAGES = ('home', 'features', 'about', 'team', 'contact', 'academy', 'academy_site')


def check_page(page):
    if page not in CONTENT_PAGES:
        raise ValidationError({'detail': 'Unknown page.'})


class PublicContent(APIView):
    """GET /content/<page>/ -> the saved overrides ({} if none). The React app merges them over its built-in defaults."""
    permission_classes = []

    def get(self, request, page):
        check_page(page)
        row = SiteContent.objects.filter(page=page).first()
        data = dict(row.data) if row else {}
        if page == 'academy':
            data.pop('till_number', None)  # till number is only revealed to registered students (see /academy/info/)
        return Response(data)


class AcademyInfo(APIView):
    """Payment details for signed-in students."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = academy_settings()
        return Response({k: cfg.get(k, '') for k in ('till_number', 'payment_instructions', 'general_rules')})


class AdminContent(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, page):
        check_page(page)
        row = SiteContent.objects.filter(page=page).first()
        return Response(row.data if row else {})

    def put(self, request, page):
        check_page(page)
        data = request.data
        if not isinstance(data, dict):
            raise ValidationError({'detail': 'Content must be a JSON object.'})
        if len(json.dumps(data)) > 200_000:
            raise ValidationError({'detail': 'Content is too large.'})
        row, _ = SiteContent.objects.update_or_create(page=page, defaults={'data': data})
        return Response(row.data)


class Track(APIView):
    """POST {vid, path}. The React app only calls this after the visitor accepted cookies."""
    permission_classes = []
    throttle_scope = 'track'

    def post(self, request):
        try:
            vid = uuid.UUID(str(request.data.get('vid')))
        except ValueError:
            raise ValidationError({'detail': 'Invalid visitor id.'})
        path = str(request.data.get('path') or '')[:200]
        user = request.user if request.user.is_authenticated else None
        v, created = Visitor.objects.get_or_create(vid=vid, defaults={'user': user, 'last_path': path, 'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200]})
        if not created:
            v.visits += 1
            v.last_path = path
            if user:
                v.user = user
            v.save()
        return Response({'detail': 'ok'})


class VisitorSer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()

    class Meta:
        model = Visitor
        fields = ['id', 'vid', 'email', 'first_seen', 'last_seen', 'visits', 'last_path', 'user_agent']

    def get_email(self, obj):
        return obj.user.email if obj.user_id else ''


class AdminUserDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserAdminSer
    queryset = User.objects.all()
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.id == request.user.id:
            return Response({'detail': 'You cannot delete yourself.'}, status=400)
        if User.objects.filter(is_staff=True).count() <= 1 and obj.is_staff:
            return Response({'detail': 'Cannot delete the last staff member.'}, status=400)
        if Payment.objects.filter(user=obj, status=Payment.Status.SUCCESS).exists():
            return Response({'detail': 'This user has successful payments. Deactivate instead to preserve financial records.'}, status=400)
        self.perform_destroy(obj)
        return Response(status=204)

    def perform_update(self, serializer):
        serializer.save()


class AdminRegistrationBulkDelete(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list):
            return Response({'detail': 'ids must be a list.'}, status=400)
        force = request.data.get('force', False)
        from .models import LessonProgress, QuizAttempt, ProjectSubmission
        regs = CourseRegistration.objects.filter(id__in=ids).select_related('user', 'course')
        deleted = []
        refused = []
        for reg in regs:
            if Payment.objects.filter(user=reg.user, course=reg.course, status=Payment.Status.SUCCESS).exists() and not force:
                refused.append(reg.id)
                continue
            LessonProgress.objects.filter(user=reg.user, lesson__module__course=reg.course).delete()
            QuizAttempt.objects.filter(user=reg.user, course=reg.course).delete()
            ProjectSubmission.objects.filter(user=reg.user, course=reg.course).delete()
            reg.delete()
            deleted.append(reg.id)
        return Response({'deleted': deleted, 'refused': refused})


class AdminRegistrationDelete(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = CourseRegistration.objects.all()
    http_method_names = ['delete', 'head', 'options']

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        force = request.query_params.get('force') == 'true'
        if Payment.objects.filter(user=obj.user, course=obj.course, status=Payment.Status.SUCCESS).exists() and not force:
            return Response({'detail': 'This registration has a successful payment. Use ?force=true to proceed.'}, status=400)
        from .models import LessonProgress, QuizAttempt, ProjectSubmission
        LessonProgress.objects.filter(user=obj.user, lesson__module__course=obj.course).delete()
        QuizAttempt.objects.filter(user=obj.user, course=obj.course).delete()
        ProjectSubmission.objects.filter(user=obj.user, course=obj.course).delete()
        self.perform_destroy(obj)
        return Response(status=204)


class AdminUserExport(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        qs = User.objects.all().order_by('-date_joined')
        rows = [[u.email, f'{u.first_name} {u.last_name}'.strip(), u.phone, 'Staff' if u.is_staff else 'Client',
                 u.date_joined.strftime('%Y-%m-%d %H:%M') if u.date_joined else '',
                 u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else ''] for u in qs]
        return csv_utils.stream_csv('users.csv', ['name', 'email', 'phone', 'role', 'joined', 'last login'], rows)


class AdminRegistrationExport(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        qs = CourseRegistration.objects.select_related('user', 'course')
        if request.query_params.get('course'):
            qs = qs.filter(course_id=request.query_params['course'])
        if request.query_params.get('status'):
            qs = qs.filter(status=request.query_params['status'])
        if request.query_params.get('payment_status'):
            qs = qs.filter(payment_status=request.query_params['payment_status'])
        rows = [[f'{r.user.first_name} {r.user.last_name}'.strip(), r.user.email, r.user.phone or '',
                 r.course.name, r.status, f'{r.progress}%', r.payment_status, r.payment_ref or '',
                 r.created_at.strftime('%Y-%m-%d %H:%M')] for r in qs]
        return csv_utils.stream_csv('students.csv', ['name', 'email', 'phone', 'course', 'status', 'progress %', 'payment status', 'payment reference', 'registered date'], rows)


class AdminPaymentExport(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        from .models import Payment
        qs = Payment.objects.select_related('user', 'course').order_by('-created_at')
        rows = [[p.created_at.strftime('%Y-%m-%d %H:%M'), p.user.email, p.course.name, p.purpose,
                 str(p.amount), p.currency, p.status, p.reference] for p in qs]
        return csv_utils.stream_csv('payments.csv', ['date', 'student', 'course', 'purpose', 'amount', 'currency', 'status', 'reference'], rows)


class AdminVisitorList(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = VisitorSer
    queryset = Visitor.objects.select_related('user')
