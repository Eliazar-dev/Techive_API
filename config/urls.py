from django.contrib import admin
from django.urls import path, include
from core import views as core
from core import status
from core import academy as ac
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
    path('api/admin/users/<int:pk>/', core.AdminUserDetail.as_view()),
    path('api/admin/users/export/', core.AdminUserExport.as_view()),
    path('api/admin/waitlist/', core.AdminWaitlistList.as_view()),
    path('api/admin/waitlist/<int:pk>/', core.AdminWaitlistDetail.as_view()),
    path('api/academy/courses/', core.PublicCourseList.as_view()),
    path('api/academy/courses/<slug:slug>/', ac.PublicCourse.as_view()),
    path('api/academy/learn/<slug:slug>/', ac.Learn.as_view()),
    path('api/academy/lessons/<int:pk>/complete/', ac.CompleteLesson.as_view()),
    path('api/academy/quiz/<slug:slug>/', ac.Quiz.as_view()),
    path('api/academy/project/<slug:slug>/', ac.SubmitProject.as_view()),
    path('api/academy/certificate/<slug:slug>/', ac.IssueCertificate.as_view()),
    path('api/certificates/<str:code>/', ac.VerifyCertificate.as_view()),
    path('api/academy/referrals/', ac.ReferralView.as_view()),
    path('api/academy/referrals/claim/', ac.ReferralClaim.as_view()),
    path('api/academy/payments/checkout/', ac.Checkout.as_view()),
    path('api/academy/payments/verify/', ac.VerifyPayment.as_view()),
    path('api/academy/payments/webhook/', ac.PaystackWebhook.as_view()),
    path('api/admin/payments/', ac.AdminPaymentList.as_view()),
    path('api/admin/payments/export/', core.AdminPaymentExport.as_view()),
    path('api/admin/projects/', ac.AdminProjectList.as_view()),
    path('api/admin/projects/<int:pk>/', ac.AdminProjectDetail.as_view()),
    path('api/admin/rewards/', ac.AdminRewardList.as_view()),
    path('api/admin/rewards/<int:pk>/', ac.AdminRewardDetail.as_view()),
    path('api/admin/sessions/', ac.AdminSessionList.as_view()),
    path('api/admin/sessions/<int:pk>/', ac.AdminSessionDetail.as_view()),
    path('api/admin/modules/', ac.AdminModuleList.as_view()),
    path('api/admin/modules/<int:pk>/', ac.AdminModuleDetail.as_view()),
    path('api/admin/lessons/', ac.AdminLessonList.as_view()),
    path('api/admin/lessons/<int:pk>/', ac.AdminLessonDetail.as_view()),
    path('api/admin/questions/', ac.AdminQuestionList.as_view()),
    path('api/admin/questions/<int:pk>/', ac.AdminQuestionDetail.as_view()),
    path('api/academy/registrations/', core.MyRegistrations.as_view()),
    path('api/academy/info/', core.AcademyInfo.as_view()),
    path('api/content/<str:page>/', core.PublicContent.as_view()),
    path('api/track/', core.Track.as_view()),
    path('api/admin/courses/', core.AdminCourseList.as_view()),
    path('api/admin/courses/<int:pk>/', core.AdminCourseDetail.as_view()),
    path('api/admin/registrations/', core.AdminRegistrationList.as_view()),
    path('api/admin/registrations/<int:pk>/', core.AdminRegistrationDetail.as_view()),
    path('api/admin/registrations/<int:pk>/delete/', core.AdminRegistrationDelete.as_view()),
    path('api/admin/registrations/bulk-delete/', core.AdminRegistrationBulkDelete.as_view()),
    path('api/admin/registrations/export/', core.AdminRegistrationExport.as_view()),
    path('api/admin/content/<str:page>/', core.AdminContent.as_view()),
    path('api/admin/visitors/', core.AdminVisitorList.as_view()),
]
