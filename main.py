#!/usr/bin/env python3
"""
Book Scraping Platform — Main Entry Point

Usage:
    python main.py run          # Run all due jobs once
    python main.py loop         # Run scheduler loop (checks every 60s)
    python main.py status       # Show job schedule status
    python main.py run JOB_NAME # Run a specific job
    python main.py enable JOB   # Enable a job
    python main.py disable JOB  # Disable a job
"""
import sys
import asyncio
import time
import logging
import importlib
import inspect
from pathlib import Path

# Load .env if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            import os
            os.environ.setdefault(_key.strip(), _val.strip())

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.use_cases import ScrapeUseCase
from adapters.inbound.scheduler_adapter import SchedulerAdapter
from adapters.outbound.engine_adapter import EngineAdapter
from adapters.outbound.exporter_adapter import ExporterAdapter
from adapters.outbound.storage_adapter import StorageAdapter

# Logging: console + file
_log_dir = Path(__file__).parent / "data" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            _log_dir / f"scrape_{Path(__file__).stem}.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def build_system():
    """Wire up all dependencies (composition root)."""
    scheduler = SchedulerAdapter()
    engine = EngineAdapter()
    exporter = ExporterAdapter()
    storage = StorageAdapter()
    use_case = ScrapeUseCase(scraper=engine, exporter=exporter, storage=storage)
    return scheduler, engine, exporter, storage, use_case


def load_category_scraper(job):
    """
    Dynamically load and instantiate a category scraper from job config.

    Reads `scraper_module` and `scraper_class` from the job, then passes
    relevant params from job.params to the scraper constructor.

    Returns (scraper_instance, run_kwargs) or (None, None) if no module configured.
    """
    module_path = getattr(job, "scraper_module", None)
    class_name = getattr(job, "scraper_class", None)
    if not module_path or not class_name:
        return None, None

    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as e:
        logger.error(f"Cannot load scraper {module_path}.{class_name}: {e}")
        return None, None

    params = job.params or {}
    run_kwargs = {}

    # Pass all params as constructor kwargs
    # (wrapper classes accept **kwargs and pick what they need)
    ctor_kwargs = dict(params)
    # Scrapers that declare rate_limit get the job's configured spacing.
    if "rate_limit" not in ctor_kwargs and "rate_limit" in inspect.signature(cls).parameters:
        ctor_kwargs["rate_limit"] = job.rate_limit

    try:
        scraper = cls(**ctor_kwargs)
    except TypeError as e:
        logger.error(f"Cannot instantiate {class_name}: {e}")
        return None, None

    # Build run() kwargs for scrapers that accept keywords at runtime
    if class_name in ("ShopeeScraper", "LazadaScraper") and "keywords" in params:
        run_kwargs["queries"] = params["keywords"]

    if "max_pages" in params:
        run_kwargs["max_pages"] = params["max_pages"]

    return scraper, run_kwargs


async def execute_job(job, use_case, engine):
    """
    Execute a single job. Uses category scraper if configured,
    otherwise falls back to generic ScrapeUseCase pipeline.
    """
    scraper, run_kwargs = load_category_scraper(job)

    if scraper:
        logger.info(f"  Using category scraper: {job.scraper_module}.{job.scraper_class}")
        try:
            results = await scraper.run(**run_kwargs)
            # Return a minimal result-like object for scheduler tracking
            # Scrapers report {"count": n, "new": m}; older ones return one row per item.
            counted = [r for r in results if isinstance(r, dict) and "count" in r]
            scraped = sum(int(r["count"]) for r in counted) if counted else len(results)
            new = sum(int(r.get("new", r["count"])) for r in counted) if counted else len(results)
            per_board: dict = {}
            hosts_down: set = set()
            for r in counted:
                for board, count in (r.get("per_board") or {}).items():
                    per_board[board] = per_board.get(board, 0) + int(count)
                hosts_down.update(r.get("down_hosts") or [])

            class CatResult:
                success = True
                items_scraped = scraped
                items_new = new
                board_counts = per_board
                down_hosts = sorted(hosts_down)
                items_cleaned = scraped
                duration_seconds = 0.0
                exported_to = []
                errors = []
            return CatResult()
        except Exception as e:
            logger.error(f"  Category scraper failed: {e}")
            class CatResultFail:
                success = False
                items_scraped = 0
                items_new = 0
                items_cleaned = 0
                duration_seconds = 0.0
                exported_to = []
                errors = [str(e)]
            return CatResultFail()
    else:
        # Fall back to generic pipeline
        if not engine.supports_engine(job.engine):
            logger.warning(f"  Engine '{job.engine}' not available, skipping")
            return None
        return await use_case.execute(job)


async def run_due_jobs():
    """Run all jobs that are currently due."""
    scheduler, engine, exporter, storage, use_case = build_system()
    pending = scheduler.get_pending_jobs()

    if not pending:
        logger.info("No jobs due. All caught up!")
        scheduler.print_schedule()
        return

    logger.info(f"Found {len(pending)} jobs due to run")
    scheduler.print_schedule()

    for job in pending:
        logger.info(f"Running: {job.name} ({job.engine} → {job.category})")
        result = await execute_job(job, use_case, engine)

        if result is None:
            continue

        scheduler.mark_completed(job.name, result)

        if result.success:
            logger.info(
                f"  ✓ {result.items_scraped} scraped, "
                f"{result.items_new} new, "
                f"{result.items_cleaned} cleaned, "
                f"{result.duration_seconds:.1f}s"
            )
            for path in result.exported_to:
                logger.info(f"  → {path}")
        else:
            logger.error(f"  ✗ Failed: {result.errors}")


async def run_single_job(job_name: str):
    """Run a specific job by name."""
    scheduler, engine, exporter, storage, use_case = build_system()

    if job_name not in scheduler.jobs:
        logger.error(f"Job not found: {job_name}")
        logger.info(f"Available jobs: {list(scheduler.jobs.keys())}")
        return

    job = scheduler.jobs[job_name]
    logger.info(f"Running: {job.name} ({job.engine} → {job.category})")
    result = await execute_job(job, use_case, engine)

    if result is None:
        return

    scheduler.mark_completed(job.name, result)

    if result.success:
        logger.info(f"✓ Done: {result.items_new} new items in {result.duration_seconds:.1f}s")
        for path in result.exported_to:
            logger.info(f"  → {path}")
    else:
        logger.error(f"✗ Failed: {result.errors}")


async def scheduler_loop(check_interval: int = 60):
    """
    Run scheduler in a continuous loop.
    Checks for due jobs every `check_interval` seconds.
    """
    logger.info(f"Starting scheduler loop (checking every {check_interval}s)")
    logger.info("Press Ctrl+C to stop\n")

    while True:
        try:
            await run_due_jobs()
            logger.info(f"Sleeping {check_interval}s until next check...\n")
            time.sleep(check_interval)
        except KeyboardInterrupt:
            logger.info("\nScheduler stopped.")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(check_interval)


def show_status():
    """Show status of all scheduled jobs."""
    scheduler, *_ = build_system()
    scheduler.print_schedule()

    # Show storage stats
    storage = StorageAdapter()
    stats = storage.get_stats()
    if stats:
        print("\n  DATA STORAGE")
        print("-" * 40)
        for collection, info in stats.items():
            print(f"  {collection:20s} | {info['count']:5d} items | last: {info['last_updated'] or 'never'}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "run":
        if len(sys.argv) > 2:
            # Run specific job
            asyncio.run(run_single_job(sys.argv[2]))
        else:
            # Run all due jobs
            asyncio.run(run_due_jobs())

    elif command == "loop":
        asyncio.run(scheduler_loop())

    elif command == "status":
        show_status()

    elif command == "enable":
        if len(sys.argv) < 3:
            logger.error("Usage: python main.py enable JOB_NAME")
            return
        scheduler, *_ = build_system()
        scheduler.enable_job(sys.argv[2])
        logger.info(f"Enabled: {sys.argv[2]}")

    elif command == "disable":
        if len(sys.argv) < 3:
            logger.error("Usage: python main.py disable JOB_NAME")
            return
        scheduler, *_ = build_system()
        scheduler.cancel(sys.argv[2])
        logger.info(f"Disabled: {sys.argv[2]}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
