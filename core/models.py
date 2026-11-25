from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Quote(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        IN_PROGRESS = 'in_progress', 'In progress'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quotes')
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    service = models.CharField(max_length=120, blank=True)
    budget = models.CharField(max_length=80, blank=True)
    message = models.TextField(max_length=5000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    notes = models.TextField(blank=True)  # internal, staff only
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.service or "General"}'


class WaitlistEntry(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150, blank=True)
    course = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'academy waitlist'

    def __str__(self):
        return self.email


class Course(models.Model):
    class Mode(models.TextChoices):
        ONLINE = 'online', 'Online'
        PHYSICAL = 'physical', 'Physical (in person)'
        HYBRID = 'hybrid', 'Hybrid (online + in person)'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open for registration'
        SOON = 'coming_soon', 'Coming soon (waitlist)'

    name = models.CharField(max_length=150)
    track = models.CharField(max_length=100, blank=True, help_text='Group label, e.g. "Building with AI"')
    description = models.TextField(blank=True)
    duration = models.CharField(max_length=60, blank=True, help_text='e.g. "6 weeks"')
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.ONLINE)
    price = models.PositiveIntegerField(null=True, blank=True, help_text='Fee in KSh to join. 0 = free to learn. Empty = "Price to be announced"')
    slug = models.SlugField(max_length=80, unique=True, null=True, blank=True, help_text='Used in links, e.g. python-programming. Filled in automatically')
    certificate_fee = models.PositiveIntegerField(default=250, help_text='KSh the student pays for the certificate. 0 = included / free')
    referral_reward = models.PositiveIntegerField(default=0, help_text='KSh the referrer earns when a friend pays to join. 0 = no reward')
    quiz_pass_mark = models.PositiveSmallIntegerField(default=70, help_text='Percent needed to pass the final quiz')
    quiz_max_attempts = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Max quiz attempts per student. Empty = unlimited')
    quiz_time_limit = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Quiz time limit in minutes. Empty = no timer')
    min_attendance = models.PositiveSmallIntegerField(default=80, help_text='Percent of live sessions a student must attend to get certified. 0 = attendance not required')
    project_title = models.CharField(max_length=150, blank=True, help_text='Title of the final project, e.g. "Build a Python CLI program"')
    project_brief = models.TextField(blank=True, help_text='Instructions for the final project students submit for the certificate. Empty = no project required')
    project_requirements = models.JSONField(default=list, blank=True, help_text='Checklist of requirements shown to students, e.g. ["Works without errors", "Has comments"]')
    next_course = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='previous_courses', help_text='Suggested next (advanced) course')
    tutor = models.CharField(max_length=150, blank=True)
    rules = models.TextField(blank=True, help_text='Shown to the student after they register')
    payment_plan = models.TextField(blank=True, help_text='Shown to the student after they register')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.name

    @property
    def needs_payment(self):
        return bool(self.price and self.price > 0)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:70] or 'course'
            slug, n = base, 2
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f'{base}-{n}', n + 1
            self.slug = slug
        super().save(*args, **kwargs)


class CourseRegistration(models.Model):
    class Status(models.TextChoices):
        REGISTERED = 'registered', 'Registered'
        ACTIVE = 'active', 'In progress'
        COMPLETED = 'completed', 'Completed'
        DROPPED = 'dropped', 'Dropped'

    class Payment(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PARTIAL = 'partial', 'Part paid'
        PAID = 'paid', 'Paid'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='registrations')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='registrations')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REGISTERED)
    progress = models.PositiveSmallIntegerField(default=0, help_text='0-100, updated by staff')
    progress_note = models.CharField(max_length=300, blank=True, help_text='Shown to the student')
    payment_status = models.CharField(max_length=10, choices=Payment.choices, default=Payment.UNPAID)
    payment_ref = models.CharField(max_length=60, blank=True, help_text='M-Pesa transaction code (till)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['user', 'course'], name='one_registration_per_course')]

    def __str__(self):
        return f'{self.user.email} -> {self.course.name}'


class SiteContent(models.Model):
    """Editable page content. `page` is home | features | about | contact | academy. `data` overrides the defaults in the React app."""
    page = models.CharField(max_length=30, unique=True)
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.page


class Visitor(models.Model):
    """Only created after the visitor clicks "Accept" on the cookie banner. No IP address is stored."""
    vid = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='visits')
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    visits = models.PositiveIntegerField(default=1)
    last_path = models.CharField(max_length=200, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-last_seen']


# ======================================================================
# Learning: lessons, quiz, project, live classes
# ======================================================================
class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=150, help_text='e.g. "Week 1: Getting started"')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.course.name}: {self.title}'


class Lesson(models.Model):
    class Kind(models.TextChoices):
        VIDEO = 'video', 'Video'
        TEXT = 'text', 'Reading'
        FILE = 'file', 'File / download'

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.TEXT)
    video_url = models.URLField(blank=True, help_text='YouTube (unlisted) or Cloudinary link for video lessons')
    body = models.TextField(blank=True, help_text='Text shown under the video, or the whole lesson for reading lessons')
    file_url = models.URLField(blank=True, help_text='Link to a PDF / starter file')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.title


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='completions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'lesson'], name='one_completion_per_lesson')]


class QuizQuestion(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField(max_length=300)
    options = models.JSONField(default=list, help_text='A list of answers, e.g. ["Yes", "No", "Maybe"]')
    correct = models.PositiveSmallIntegerField(default=0, help_text='Number of the right answer in the list above, starting at 0 (first answer = 0)')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.text[:60]


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='attempts')
    score = models.PositiveSmallIntegerField()
    passed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ProjectSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Waiting for review'
        APPROVED = 'approved', 'Approved'
        CHANGES = 'changes', 'Needs changes'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='projects')
    link = models.URLField(blank=True, max_length=500)
    notes = models.TextField(blank=True, max_length=3000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    feedback = models.TextField(blank=True, max_length=2000, help_text='Shown to the student')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [models.UniqueConstraint(fields=['user', 'course'], name='one_project_per_course')]


class LiveSession(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    title = models.CharField(max_length=150)
    starts_at = models.DateTimeField()
    meet_url = models.URLField(blank=True, help_text='Google Meet link')
    notes = models.TextField(blank=True)
    recording_url = models.URLField(blank=True, help_text='Add after the class so students can watch again')
    notes_pdf = models.BinaryField(null=True, blank=True, help_text='Class notes PDF uploaded by admin')
    notes_pdf_name = models.CharField(max_length=200, blank=True)
    archived = models.BooleanField(default=False, help_text='Hidden from lists but attendance records are preserved')
    hidden = models.BooleanField(default=False, help_text='Hidden from students but still visible to admin')

    class Meta:
        ordering = ['starts_at']

    def __str__(self):
        return f'{self.course.name}: {self.title}'


class AttendanceToken(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Token for {self.session.title}'


class Attendance(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance')
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='attendances')
    checked_in_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verification_method = models.CharField(max_length=20, default='link')

    class Meta:
        unique_together = ['user', 'session']
        ordering = ['-checked_in_at']

    def __str__(self):
        return f'{self.user.email} - {self.session.title}'


# ======================================================================
# Money: payments, certificates, referrals
# ======================================================================
class Payment(models.Model):
    class Purpose(models.TextChoices):
        ENROLLMENT = 'enrollment', 'Course fee'
        CERTIFICATE = 'certificate', 'Certificate fee'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Paid'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='payments')
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    amount = models.PositiveIntegerField(help_text='Whole KSh')
    currency = models.CharField(max_length=3, default='KES')
    reference = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    channel = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} {self.amount} {self.status}'


class Certificate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='certificates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='certificates')
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200, help_text='Name printed on the certificate')
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']
        constraints = [models.UniqueConstraint(fields=['user', 'course'], name='one_certificate_per_course')]

    def __str__(self):
        return self.code


class ReferralProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_profile')
    code = models.CharField(max_length=12, unique=True)
    referred_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='referred_users')


class ReferralReward(models.Model):
    class Status(models.TextChoices):
        EARNED = 'earned', 'Earned (not yet paid out)'
        PAID = 'paid', 'Paid out'

    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='rewards')
    referred = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='+')
    amount = models.PositiveIntegerField(help_text='Whole KSh')
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.EARNED)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['referred', 'course'], name='one_reward_per_referred_course')]
