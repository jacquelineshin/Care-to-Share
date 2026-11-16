
from django.contrib import admin
from django.urls import path, include

from ai_services.health import healthz
from config.login_throttle import ThrottledLoginView

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("", include("appointments.urls")),
    # Must come before the auth include so it replaces the default login view.
    path("accounts/login/", ThrottledLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
]
