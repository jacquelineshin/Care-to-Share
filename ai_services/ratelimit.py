"""
Per-user rate limiting for AI endpoints.

Each recommendation request runs the embedding model, so an abusive or
buggy client could monopolise the CPU. A fixed one-minute window per
user (or per IP for anonymous requests) keeps inference capacity fair.
"""

import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render


def _client_key(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "unknown")
    return f"ip:{ip}"


def ai_rate_limit(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        limit = getattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 20)
        window = int(time.time() // 60)
        key = f"ai-rl:{view.__name__}:{_client_key(request)}:{window}"

        if cache.add(key, 1, timeout=70):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:  # key expired between add and incr
                cache.set(key, 1, timeout=70)
                count = 1

        if count > limit:
            response = render(
                request,
                "appointments/rate_limited.html",
                status=429,
            )
            response["Retry-After"] = "60"
            return response

        return view(request, *args, **kwargs)

    return wrapper
