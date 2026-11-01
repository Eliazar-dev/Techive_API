from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, EmailOTP


@admin.register(User)
class TechiveUserAdmin(UserAdmin):
    ordering = ('-date_joined',)
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name')
    fieldsets = ((None, {'fields': ('email', 'password')}),
                 ('Profile', {'fields': ('first_name', 'last_name', 'phone', 'avatar_url', 'email_verified', 'signup_source')}),
                 ('Access', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}))
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('email', 'password1', 'password2')}),)


admin.site.register(EmailOTP)
