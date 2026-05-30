from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render


def homepage(request):
    return render(request, 'home/index.html')


@user_passes_test(lambda user: user.is_staff, login_url="staff-login")
def feedback_triage(request):
    return render(request, "home/feedback_triage.html")
