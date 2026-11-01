from django.conf import settings
from django.db import models


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
    price = models.PositiveIntegerField(null=True, blank=True, help_text='Fee in KSh. Empty = "Price to be announced"')
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
