import os
from celery import Celery

# Get Redis URL from environment variable, with a default for local testing
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "mcbom_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["mcbom.worker.tasks"] # Pre-discover tasks from this module
)

celery_app.conf.update(
    task_track_started=True,
)
