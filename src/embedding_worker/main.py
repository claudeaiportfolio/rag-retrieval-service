"""embedding-worker: RQ worker — drains the embed-jobs queue, runs ingestion.

One worker per pod (KEDA scales pods on Redis list depth), so we use RQ's
SimpleWorker (no fork): the pod is the isolation boundary. The job itself lives
in `tasks.process_document`.
"""

from __future__ import annotations

import logging

from rq import SimpleWorker

from common.config import settings
from common.otel import setup_telemetry
from platform_core.queue import RedisSettings, redis_connection

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        username=settings.redis_username or None,
        password=settings.redis_password or None,
        use_tls=settings.redis_use_tls,
        ssl_ca_certs=settings.redis_ca_path or None,
    )


def main() -> None:
    setup_telemetry("embedding-worker")
    connection = redis_connection(_redis_settings())
    logger.info("event=worker_starting queue=%s", settings.rq_queue_name)
    # with_scheduler=True so RQ's Retry (set at enqueue) actually re-enqueues
    # failed jobs at their scheduled time — without it, retries sit inert in the
    # ScheduledJobRegistry and never run.
    SimpleWorker([settings.rq_queue_name], connection=connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
