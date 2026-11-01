from django.contrib import admin
from django.urls import path, include
from core import views as core
from core import status
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Always return {"detail": "..."} so the frontend has one error shape."""
    resp = exception_handler(exc, context)
    if resp is not None and isinstance(resp.data, dict) and 'detail' not in resp.data:
        first = next(iter(resp.data.values()), 'Invalid request')
        if isinstance(first, (list, tuple)) and first:
            first = first[0]
        resp.data = {'detail': str(first), 'errors': resp.data}
    return resp


urlpatterns = [
    path('', status.status_page),            # animated "API is running" page
    path('api/health/', status.health),      # JSON used by that page and by uptime monitors
    path('django-admin/', admin.site.urls),  # built-in Django admin (backup tool)
    path('api/auth/', include('accounts.urls')),
    path('api/quotes/', core.QuoteCreate.as_view()),
    path('api/academy/waitlist/', core.WaitlistCreate.as_view()),
    path('api/admin/stats/', core.AdminStats.as_view()),
    path('api/admin/quotes/', core.AdminQuoteList.as_view()),
    path('api/admin/quotes/<int:pk>/', core.AdminQuoteDetail.as_view()),
    path('api/admin/users/', core.AdminUserList.as_view()),
    path('api/admin/waitlist/', core.AdminWaitlistList.as_view()),
    path('api/admin/waitlist/<int:pk>/', core.AdminWaitlistDetail.as_view()),
    path('api/academy/courses/', core.PublicCourseList.as_view()),
    path('api/academy/registrations/', core.MyRegistrations.as_view()),
    path('api/academy/info/', core.AcademyInfo.as_view()),
    path('api/content/<str:page>/', core.PublicContent.as_view()),
    path('api/track/', core.Track.as_view()),
    path('api/admin/courses/', core.AdminCourseList.as_view()),
    path('api/admin/courses/<int:pk>/', core.AdminCourseDetail.as_view()),
    path('api/admin/registrations/', core.AdminRegistrationList.as_view()),
    path('api/admin/registrations/<int:pk>/', core.AdminRegistrationDetail.as_view()),
    path('api/admin/content/<str:page>/', core.AdminContent.as_view()),
    path('api/admin/visitors/', core.AdminVisitorList.as_view()),
]
