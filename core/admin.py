from django.contrib import admin
from .models import Quote, WaitlistEntry


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'service', 'budget', 'status', 'created_at')
    list_filter = ('status', 'service')
    search_fields = ('name', 'email', 'message')
    list_editable = ('status',)


@admin.register(WaitlistEntry)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'course', 'created_at')
    search_fields = ('email', 'name')


from .models import Course, CourseRegistration, SiteContent, Visitor  # noqa: E402


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'track', 'duration', 'mode', 'price', 'status', 'is_published', 'order')
    list_editable = ('status', 'is_published', 'order')


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'status', 'progress', 'payment_status', 'created_at')
    list_filter = ('course', 'status', 'payment_status')


admin.site.register(SiteContent)
admin.site.register(Visitor)
