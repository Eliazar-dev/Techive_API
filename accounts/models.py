import hashlib, hmac
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _make(self, email, password=None, **extra):
        if not email:
            raise ValueError('Email is required')
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # Google / Microsoft accounts have no password until they set one
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        return self._make(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        return self._make(email, password, is_staff=True, is_superuser=True, email_verified=True, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=40, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)  # profile photo (from Google); empty = show initials
    email_verified = models.BooleanField(default=False)
    signup_source = models.CharField(max_length=10, default='email')  # email | google | microsoft
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email


class EmailOTP(models.Model):
    """One-time code. Only a keyed hash of the code is stored. `purpose` stops a code made for one flow being used in another."""
    PURPOSES = [('login', 'login'), ('signup', 'signup'), ('reset', 'reset')]
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=10, choices=PURPOSES, default='login')
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def digest(email, purpose, code):
        msg = f'{email}:{purpose}:{code}'.encode()
        return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
