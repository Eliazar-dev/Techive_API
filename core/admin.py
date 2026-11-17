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


from .models import (Certificate, Lesson, LiveSession, Module, Payment, ProjectSubmission, QuizQuestion,  # noqa: E402
                     ReferralProfile, ReferralReward)


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    show_change_link = True


class QuizInline(admin.StackedInline):
    model = QuizQuestion
    extra = 0


class SessionInline(admin.TabularInline):
    model = LiveSession
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'duration', 'price', 'certificate_fee', 'referral_reward', 'status', 'is_published', 'order')
    list_editable = ('status', 'is_published', 'order')
    inlines = [ModuleInline, QuizInline, SessionInline]


class LessonInline(admin.StackedInline):
    model = Lesson
    extra = 0


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    inlines = [LessonInline]


admin.site.register(Payment)
admin.site.register(ProjectSubmission)
admin.site.register(Certificate)
admin.site.register(ReferralProfile)
admin.site.register(ReferralReward)


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'status', 'progress', 'payment_status', 'created_at')
    list_filter = ('course', 'status', 'payment_status')


admin.site.register(SiteContent)
admin.site.register(Visitor)
