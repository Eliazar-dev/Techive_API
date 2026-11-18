from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.Register.as_view()),
    path('login/', views.Login.as_view()),
    path('otp/verify/', views.OTPVerify.as_view()),
    path('otp/request/', views.OTPRequest.as_view()),      # "resend code"
    path('password/forgot/', views.PasswordForgot.as_view()),
    path('password/reset/', views.PasswordReset.as_view()),
    path('google/', views.GoogleAuth.as_view()),
    path('microsoft/', views.MicrosoftAuth.as_view()),
    path('token/refresh/', views.TokenRefreshWithActiveCheck.as_view()),
    path('me/', views.Me.as_view()),
]
