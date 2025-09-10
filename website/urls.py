from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('home.urls')),  # Add this line
    path('admin/', admin.site.urls),
]