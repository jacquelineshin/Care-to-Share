"""
Brute-force protection for the login page.

Care to Share accounts hold personal health information, so repeated
password guessing is a realistic threat. After LOGIN_MAX_FAILURES failed
attempts for the same username *or* from the same IP address within
LOGIN_LOCKOUT_SECONDS, further attempts are refused with HTTP 429 until
the window expires. A successful login clears the username's counter.

Counters live in the Django cache (per-process LocMemCache locally;
use Redis when running several instances).
"""

import hashlib
import logging

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.cache import cache


logger = logging.getLogger(__name__)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "unknown")


def _keys(request):
    username = request.POST.get("username", "").strip().lower()
    # Hash the username so cache keys and logs never contain it verbatim.
    user_hash = hashlib.sha256(username.encode()).hexdigest()[:16]
    return [f"login-fail:user:{user_hash}", f"login-fail:ip:{_client_ip(request)}"]


def _increment(key, timeout):
    if cache.add(key, 1, timeout=timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, timeout=timeout)
        return 1


class ThrottledLoginView(LoginView):

    def _limits(self):
        return (
            getattr(settings, "LOGIN_MAX_FAILURES", 5),
            getattr(settings, "LOGIN_LOCKOUT_SECONDS", 300),
        )

    def post(self, request, *args, **kwargs):
        max_failures, lockout = self._limits()

        if any((cache.get(key) or 0) >= max_failures for key in _keys(request)):
            logger.warning("login.locked ip=%s", _client_ip(request))
            form = self.get_form()
            form.errors.clear()
            form.add_error(
                None,
                f"Too many failed login attempts. Please wait "
                f"{lockout // 60} minutes and try again.",
            )
            response = self.render_to_response(self.get_context_data(form=form))
            response.status_code = 429
            response["Retry-After"] = str(lockout)
            return response

        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        _, lockout = self._limits()
        for key in _keys(self.request):
            _increment(key, lockout)
        logger.info("login.failed ip=%s", _client_ip(self.request))
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(_keys(self.request)[0])
        return super().form_valid(form)
