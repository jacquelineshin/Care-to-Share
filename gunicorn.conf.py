"""
Gunicorn settings for production.

The embedding model needs ~300-400 MB RAM per process, so we run a
single worker process with several threads instead of many workers
(each worker would hold its own copy of the model).
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60
accesslog = "-"
errorlog = "-"


def post_worker_init(worker):
    """Load the model when the worker starts, not on the first request."""
    try:
        from ai_services.resource_recommender import get_embedding_model

        get_embedding_model()
        worker.log.info("Embedding model loaded.")
    except Exception as exc:  # the app still works; recommendations fail gracefully
        worker.log.warning("Embedding model warm-up failed: %s", exc)
