"""
Celery configuration — Redis as both broker and result backend.

Usage
-----
from celery_config import celery_app

@celery_app.task
def my_task(): ...
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "xlventures",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        # Register task modules here, e.g.:
        # "app.tasks.enrichment",
        # "app.tasks.scoring",
    ],
)

celery_app.conf.update(
    # ── Serialisation ──────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Timezone ───────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,
    # ── Result TTL ─────────────────────────────────────────────────────────
    result_expires=3_600,          # 1 hour
    result_backend_transport_options={
        "retry_policy": {
            "timeout": 5.0,
        }
    },
    # ── Reliability ────────────────────────────────────────────────────────
    task_acks_late=True,           # acknowledge only after task completes
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # fair dispatch for long-running tasks
    # ── Retries ────────────────────────────────────────────────────────────
    task_max_retries=3,
    task_default_retry_delay=60,   # 60 s between retries
    # ── Queues ─────────────────────────────────────────────────────────────
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "enrichment": {"exchange": "enrichment", "routing_key": "enrichment"},
        "scoring": {"exchange": "scoring", "routing_key": "scoring"},
    },
    # ── Monitoring ─────────────────────────────────────────────────────────
    worker_send_task_events=True,
    task_send_sent_event=True,
)
