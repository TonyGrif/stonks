"""Entry point: loads config, sets up logging, and starts the APScheduler."""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Callable

import yaml
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_SCHEDULER_STARTED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import db
import fetcher


def setup_logging() -> None:
    """Configure dual-sink logging to stdout and a rotating file.

    Creates ``logs/stonks.log`` with daily rotation and a 7-day retention
    window. Both sinks use the same structured format so log lines are
    identical whether read from ``docker compose logs`` or the file.
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stdout),
        TimedRotatingFileHandler(
            log_dir / "stonks.log",
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def register_listeners(scheduler: BlockingScheduler) -> None:
    """Attach event listeners that log schedule status to the scheduler.

    Two listeners are registered:

    * ``EVENT_SCHEDULER_STARTED`` — logs the first ``next_run_time`` for
      every job once the scheduler has initialised and computed its initial
      fire times.
    * ``EVENT_JOB_EXECUTED | EVENT_JOB_ERROR`` — logs the next scheduled
      run time after every job execution so the log shows a continuous
      record of when each ticker will fetch next.

    Args:
        scheduler: The ``BlockingScheduler`` instance to attach listeners to.
    """
    logger = logging.getLogger("scheduler")

    def on_started(_event) -> None:
        for job in scheduler.get_jobs():
            logger.info("[%s] next run: %s", job.id, job.next_run_time)

    def on_executed(event) -> None:
        job = scheduler.get_job(event.job_id)
        if job:
            logger.info("[%s] next run: %s", job.id, job.next_run_time)

    scheduler.add_listener(on_started, EVENT_SCHEDULER_STARTED)
    scheduler.add_listener(on_executed, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)


def make_job(symbol: str, fields: list[str], period: str, interval: str) -> Callable:
    """Create a scheduler-compatible job function for a single ticker.

    The returned callable fetches ``fields`` for ``symbol`` via
    :func:`fetcher.fetch` and persists the result via :func:`db.upsert`.
    Exceptions are caught and logged so a single ticker failure does not
    crash the scheduler or affect other tickers.

    Args:
        symbol: The ticker symbol to fetch (e.g. ``"AAPL"``).
        fields: List of field names to retrieve on each invocation.
        period: How far back to fetch (e.g. ``"1d"``, ``"5d"``). Passed
            through to :func:`fetcher.fetch`.
        interval: Bar size (e.g. ``"1d"``, ``"5m"``). Passed through to
            :func:`fetcher.fetch`.

    Returns:
        A zero-argument callable suitable for use as an APScheduler job.
        Its ``__name__`` is set to ``fetch_{symbol}`` for log clarity.
    """
    def job() -> None:
        logger = logging.getLogger("job")
        logger.info("[%s] fetch started (period=%s, interval=%s)", symbol, period, interval)
        try:
            data = fetcher.fetch(symbol, fields, period, interval)
            db.upsert(symbol, data)
            logger.info("[%s] fetch complete", symbol)
        except Exception as e:
            logger.error("[%s] fetch failed: %s", symbol, e)

    job.__name__ = f"fetch_{symbol}"
    return job


def main() -> None:
    """Bootstrap the application and start the blocking scheduler.

    Execution order:
        1. Configure logging.
        2. Load ``config.yaml`` (or the path in ``CONFIG_PATH``).
        3. Ensure the database schema exists.
        4. Register one APScheduler cron job per ticker entry.
           ``period`` and ``interval`` default to ``"1d"`` if omitted.
           ``settings.timezone`` (default ``"UTC"``) is applied to all
           cron expressions so schedules can be written in exchange local
           time; bar timestamps are still stored as UTC in the database.
        5. Attach event listeners for startup and post-execution logging.
        6. If ``settings.run_on_startup`` is ``true``, run all jobs once
           immediately before handing control to the scheduler.
        7. Start the blocking scheduler (runs until process is killed).
    """
    setup_logging()
    logger = logging.getLogger("main")

    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info("ensuring database schema")
    db.ensure_schema()

    settings = config.get("settings", {})
    run_on_startup = settings.get("run_on_startup", False)
    timezone = settings.get("timezone", "UTC")

    scheduler = BlockingScheduler()
    register_listeners(scheduler)

    for entry in config["tickers"]:
        symbol = entry["symbol"]
        fields = entry["fields"]
        schedule = entry["schedule"]
        period = entry.get("period", "1d")
        interval = entry.get("interval", "1d")

        job = make_job(symbol, fields, period, interval)
        scheduler.add_job(job, CronTrigger.from_crontab(schedule, timezone=timezone), id=symbol)
        logger.info(
            "[%s] registered — schedule: %s (%s), period: %s, interval: %s — fields: %s",
            symbol, schedule, timezone, period, interval, fields,
        )

        if run_on_startup:
            logger.info("[%s] run_on_startup triggered", symbol)
            job()

    logger.info("scheduler starting")
    scheduler.start()


if __name__ == "__main__":
    main()
