"""Hosted capture run (GitHub Actions): job set, tracker off, quiet public log."""
import io
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import cloud_capture  # noqa: E402
from adapters.inbound.scheduler_adapter import SchedulerAdapter  # noqa: E402
from core.models import ScrapeJob  # noqa: E402


def _job(name, **params):
    return ScrapeJob(name=name, category="sales", engine="local", url="", schedule="0 */6 * * *", params=params)


class _Result:
    def __init__(self, success, scraped=0, new=0, errors=()):
        self.success = success
        self.items_scraped = scraped
        self.items_new = new
        self.errors = list(errors)


class CloudJobsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        state = Path(self._tmp.name) / "schedule_state.json"
        self.jobs = SchedulerAdapter(state_path=state).jobs

    def tearDown(self):
        self._tmp.cleanup()

    def test_runs_the_three_job_steps_in_pipeline_order(self):
        names = [job.name for job in cloud_capture.cloud_jobs(self.jobs)]
        self.assertEqual(names, ["job_postings", "career_postings", "job_match_filter"])

    def test_every_cloud_job_is_configured_and_enabled(self):
        for name in cloud_capture.CLOUD_JOBS:
            self.assertIn(name, self.jobs)
            self.assertTrue(self.jobs[name].enabled, name)

    def test_match_filter_never_seeds_the_private_apply_tracker(self):
        jobs = {job.name: job for job in cloud_capture.cloud_jobs(self.jobs)}
        self.assertIs(jobs["job_match_filter"].params["seed_tracker"], False)
        self.assertTrue(self.jobs["job_match_filter"].params.get("seed_tracker"))  # config object untouched

    def test_missing_job_fails_loudly(self):
        with self.assertRaises(KeyError):
            cloud_capture.cloud_jobs({"job_postings": _job("job_postings")})


class RunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.log = Path(self._tmp.name) / "logs" / "cloud-capture.log"

    def tearDown(self):
        self._tmp.cleanup()

    def test_job_output_goes_to_the_private_log_not_the_console(self):
        async def execute(job):
            print("PRIVATE stdout: Senior Python Engineer at Example")
            print("PRIVATE stderr", file=sys.stderr)
            return _Result(True, scraped=7, new=3)

        console = io.StringIO()
        with redirect_stdout(console):
            code = cloud_capture.run([_job("job_postings")], execute, log_path=self.log)
        self.assertEqual(code, 0)
        self.assertNotIn("PRIVATE", console.getvalue())
        self.assertIn("job_postings: ok scraped=7 new=3", console.getvalue())
        log = self.log.read_text(encoding="utf-8")
        self.assertIn("PRIVATE stdout", log)
        self.assertIn("PRIVATE stderr", log)

    def test_a_failed_job_fails_the_run_but_later_jobs_still_run(self):
        ran = []

        async def execute(job):
            ran.append(job.name)
            if job.name == "career_postings":
                return _Result(False, errors=["board unavailable"])
            return _Result(True, scraped=1, new=1)

        code = cloud_capture.run(
            [_job("job_postings"), _job("career_postings"), _job("job_match_filter")], execute, log_path=self.log
        )
        self.assertEqual(code, 1)
        self.assertEqual(ran, ["job_postings", "career_postings", "job_match_filter"])

    def test_an_exception_or_skipped_job_counts_as_failure(self):
        async def boom(job):
            raise RuntimeError("network down")

        async def skipped(job):
            return None

        self.assertEqual(cloud_capture.run([_job("job_postings")], boom, log_path=self.log), 1)
        self.assertEqual(cloud_capture.run([_job("job_postings")], skipped, log_path=self.log), 1)


class ErrorReportingTest(unittest.TestCase):
    """Failures reach Sentry (private); the public console still gets counts only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.log = Path(self._tmp.name) / "logs" / "cloud-capture.log"
        self.reported = []
        patches = [
            mock.patch.object(cloud_capture._sentry, "capture_exception", lambda exc: self.reported.append(exc)),
            mock.patch.object(
                cloud_capture._sentry, "capture_failure", lambda name, error: self.reported.append((name, error))
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def test_an_exception_is_reported_with_the_original_exception(self):
        error = RuntimeError("network down")

        async def boom(job):
            raise error

        cloud_capture.run([_job("job_postings")], boom, log_path=self.log)
        self.assertEqual(self.reported, [error])

    def test_a_failed_or_skipped_result_is_reported_by_job_name(self):
        async def failed(job):
            if job.name == "job_postings":
                return _Result(False, errors=["board unavailable", "timeout"])
            return None

        cloud_capture.run([_job("job_postings"), _job("career_postings")], failed, log_path=self.log)
        self.assertEqual(
            self.reported,
            [("job_postings", "board unavailable; timeout"), ("career_postings", "skipped (engine unavailable)")],
        )

    def test_a_successful_run_reports_nothing(self):
        async def ok(job):
            return _Result(True, scraped=2, new=0)

        self.assertEqual(cloud_capture.run([_job("job_postings")], ok, log_path=self.log), 0)
        self.assertEqual(self.reported, [])


class IngestInputsTest(unittest.TestCase):
    def test_lists_only_existing_capture_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "job_postings.csv").write_text("title\n", encoding="utf-8")
            (data / "apply_tracker.csv").write_text("title\n", encoding="utf-8")
            self.assertEqual(cloud_capture.ingest_inputs(data), [data / "job_postings.csv"])
            (data / "matched_jobs.csv").write_text("title\n", encoding="utf-8")
            self.assertEqual(
                cloud_capture.ingest_inputs(data), [data / "job_postings.csv", data / "matched_jobs.csv"]
            )


if __name__ == "__main__":
    unittest.main()
