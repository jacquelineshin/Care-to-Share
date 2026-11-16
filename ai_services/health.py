from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """
    Liveness/readiness probe for the hosting platform. Checks the
    database but deliberately does not load the AI model, so the probe
    stays fast and cheap.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return JsonResponse(
        {"status": "ok" if db_ok else "degraded", "database": db_ok},
        status=200 if db_ok else 503,
    )
