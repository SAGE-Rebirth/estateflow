from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers import jobs


async def startup(ctx) -> None:
    configure_logging()
    await jobs.startup_indexes(ctx)


class WorkerSettings:
    functions = [
        jobs.ingest_document,
        jobs.index_property,
        jobs.process_inbound_message,
        jobs.process_status_update,
    ]
    cron_jobs = [
        cron(jobs.reminders_cron, minute=set(range(0, 60, 5)), run_at_startup=True),
        # Hourly; the job itself only acts for tenants where it's 07:xx local time.
        cron(jobs.digest_cron, minute={2}),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
    job_timeout = 300
    max_tries = 3
