from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import StaffAuthenticationForm

urlpatterns = [
    path('', views.homepage, name='home'),
    path(
        'studio-access/',
        LoginView.as_view(
            authentication_form=StaffAuthenticationForm,
            next_page='feedback-triage',
            template_name='home/staff_login.html',
        ),
        name='staff-login',
    ),
    path('studio-exit/', LogoutView.as_view(next_page='home'), name='staff-logout'),
    path('feedback-triage/', views.feedback_triage, name='feedback-triage'),
]
