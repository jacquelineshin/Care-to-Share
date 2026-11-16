
from django.contrib import admin
from django.urls import path, include

from ai_services.health import healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("", include("appointments.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
]
