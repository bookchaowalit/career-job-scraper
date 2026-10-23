#!/usr/bin/env python3
"""Hosted capture run for GitHub Actions (.github/workflows/scheduled-capture.yml).

Runs the job-discovery steps once, in pipeline order, then lists the capture
files that book-job-data should ingest into the R2 lake.

The repository is public, so the Actions log is public too:

* Job output (titles, match scores, keywords) goes to ``data/logs/cloud-capture.log``,
  which is never uploaded. The console gets one status line per job.
* ``job_match_filter`` runs with ``seed_tracker`` off: the private
  ``apply_tracker.csv`` stays a local-only file.
* No Telegram alerts: Railway job-radar already alerts on the same boards.
* Failures go to Sentry when SENTRY_DSN is set (scripts/_sentry.py: errors only,
  allowlist scrub); without it nothing is sent.

Usage:
  python scripts/cloud_capture.py           # run the jobs; exit 1 if any failed
  python scripts/cloud_capture.py --inputs  # print ingest inputs, one per line
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Coroutine, Iterator, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _sentry  # noqa: E402
from repo_paths import DATA_DIR  # noqa: E402

CLOUD_JOBS = ("job_postings", "career_postings", "job_match_filter")
PARAM_OVERRIDES = {"job_match_filter": {"seed_tracker": False}}
INGEST_FILES = ("job_postings.csv", "matched_jobs.csv")
LOG_FILE = DATA_DIR / "logs" / "cloud-capture.log"
ERROR_CHARS = 200


def cloud_jobs(jobs: dict[str, Any]) -> list[Any]:
    """The configured jobs to run, with hosted-run overrides on copies."""
    return [
        replace(jobs[name], params={**(jobs[name].params or {}), **PARAM_OVERRIDES.get(name, {})})
        for name in CLOUD_JOBS
    ]


def ingest_inputs(data_dir: Path = DATA_DIR) -> list[Path]:
    return [data_dir / name for name in INGEST_FILES if (data_dir / name).is_file()]


@contextmanager
def _to_log(log_path: Path) -> Iterator[None]:
    """Send fd 1 and 2 (prints, logging handlers, children) to the private log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    saved_streams = (sys.stdout, sys.stderr)
    with log_path.open("a", encoding="utf-8") as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        sys.stdout = sys.stderr = log
        try:
            yield
        finally:
            log.flush()
            sys.stdout, sys.stderr = saved_streams
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            for fd in saved:
                os.close(fd)


def run(
    jobs: Sequence[Any],
    execute: Callable[[Any], Coroutine[Any, Any, Any]],
    *,
    log_path: Path = LOG_FILE,
) -> int:
    code = 0
    for job in jobs:
        error: str | None = None
        result: Any = None
        try:
            with _to_log(log_path):
                result = asyncio.run(execute(job))
        except Exception as exc:  # one broken job must not stop the rest
            result, error = None, f"{type(exc).__name__}: {exc}"
            _sentry.capture_exception(exc)
        if result is not None and result.success:
            print(f"{job.name}: ok scraped={result.items_scraped} new={result.items_new}", flush=True)
            continue
        code = 1
        if error is None:
            error = "; ".join(result.errors) if result is not None else "skipped (engine unavailable)"
            _sentry.capture_failure(job.name, error)
        print(f"{job.name}: failed: {error[:ERROR_CHARS]}", flush=True)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inputs", action="store_true", help="print ingest inputs and exit")
    args = parser.parse_args(argv)
    if args.inputs:
        for path in ingest_inputs():
            print(path)
        return 0

    _sentry.init_sentry()
    try:
        return _capture()
    finally:
        _sentry.flush()


def _capture() -> int:
    with _to_log(LOG_FILE):  # main.py configures logging handlers on import
        import main as scraper_main

        scheduler, engine, _exporter, _storage, use_case = scraper_main.build_system()
    jobs = cloud_jobs(scheduler.jobs)

    async def execute(job: Any) -> Any:
        result = await scraper_main.execute_job(job, use_case, engine)
        if result is not None:
            scheduler.mark_completed(job.name, result)
        return result

    return run(jobs, execute)


if __name__ == "__main__":
    raise SystemExit(main())
