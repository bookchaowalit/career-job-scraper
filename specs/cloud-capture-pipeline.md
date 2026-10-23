---
title: SPEC-CAP — Hosted cloud capture pipeline (Track B)
status: implemented (describes behaviour on main, 2026-10-23)
created: 2026-10-23
related: [../DOCPACK/05-srs.md, ../DOCPACK/07-test-uat.md, ../RUNBOOK.md, ../docs/measurement/KPI-PLAN.md]
---

# SPEC-CAP — Hosted cloud capture pipeline

Specification of the existing hosted capture: what it does, what it must never
do, and how each rule is checked. It refines DOCPACK SRS requirements FR-02
(board capture), FR-03 (career discovery), FR-04 (targeting policy), FR-13
(export to `book-job-data`) for the GitHub Actions runtime.

## Context

- Workflow: `.github/workflows/scheduled-capture.yml` (name "Scheduled capture
  and deploy to R2 (Track B)"), GitHub-hosted `ubuntu-24.04`, public repo.
- Entry point: `scripts/cloud_capture.py`.
- Consumer: `book-job-data-api` (Railway) reads R2 prefix
  `portfolio-demo/book-job-data-001`. The "deploy" of this repo is the data it
  publishes there; there is no server.
- Track A (Railway `job-radar`, hourly, Telegram alerts) is a separate system.

## Requirements

| ID | Requirement | Verified by |
|---|---|---|
| SPEC-CAP-01 | Trigger: cron `17 */6 * * *` (UTC) and `workflow_dispatch`; one run at a time (`concurrency: scheduled-capture`, no cancel); 30-minute job timeout. | Workflow file review |
| SPEC-CAP-02 | Install from the reviewed resolution only: `uv sync --frozen --no-dev` (uv.lock); `book-job-data` from a pinned commit (`BOOK_JOB_DATA_REF`) in a separate venv. | Workflow file; run log "Install scraper" |
| SPEC-CAP-03 | Run exactly `job_postings`, `career_postings`, `job_match_filter`, in that order, each once, with `job_match_filter.seed_tracker = false` on a copy (config object unchanged). A missing job in `config/jobs.yaml` fails loudly. | `tests/test_cloud_capture.py::CloudJobsTest` |
| SPEC-CAP-04 | Public log = counts only: all job output (stdout, stderr, logging, child processes) goes to `data/logs/cloud-capture.log`, never uploaded. The console gets one line per job: `<job>: ok scraped=N new=M` or `<job>: failed: <error, max 200 chars>`. | `RunTest.test_job_output_goes_to_the_private_log_not_the_console`; manual review of a run log |
| SPEC-CAP-05 | Failure isolation: an exception, a failed result or a skipped job (`None`) marks the run failed (exit 1) but later jobs still run. | `RunTest.test_a_failed_job_fails_the_run_but_later_jobs_still_run`, `test_an_exception_or_skipped_job_counts_as_failure` |
| SPEC-CAP-06 | Ingest whatever landed, even after a partial capture: `--inputs` lists only existing `job_postings.csv` and `matched_jobs.csv` (never `apply_tracker.csv`); zero inputs fails the ingest step. The ingest prints dataset names and record counts only. | `IngestInputsTest`; workflow step `Ingest into R2` |
| SPEC-CAP-07 | Every run (also on failure or cancel) posts `{ok, failed: [capture?, ingest?]}` to the uptime Worker heartbeat `job-capture` (alert at once on failure, or after 13 h of silence). | Workflow step `Heartbeat` |
| SPEC-CAP-08 | Error reporting: with `SENTRY_DSN` set, each exception (with its traceback) and each failed or skipped job (message `<job>: failed: <error>`, tag `job`) goes to Sentry; errors only (no tracing, logs or breadcrumbs); allowlist scrub drops request, user, extra, breadcrumbs, frame locals, non-platform contexts, unknown top-level keys and URL query strings, and masks secrets. Without `SENTRY_DSN` nothing is imported or sent. | `tests/test_sentry_scrub.py`; `tests/test_cloud_capture.py::ErrorReportingTest` |
| SPEC-CAP-09 | Carry only `data/job_postings_history.csv` (public postings) between runs, via the Actions cache, so `new=` counts stay meaningful. | Workflow steps `Restore/Save capture history` |
| SPEC-CAP-10 | No private material on the runner: no apply tracker, no Telegram job alerts, no credentials other than the R2 write token (bucket-scoped), heartbeat token and Sentry DSN, all from repo secrets. | Workflow review; `SAFETY.md` |

## Acceptance criteria

```gherkin
Scenario: normal run
  Given the three cloud jobs are configured and enabled
  When the scheduled workflow runs
  Then the log shows three "ok scraped=N new=M" lines and no job titles
  And book-job-data reports record counts for job_postings and matched_jobs
  And the heartbeat posts {"ok": true, "failed": []}

Scenario: one board is down
  Given career_postings raises an exception
  When the workflow runs
  Then job_postings and job_match_filter still run
  And the capture step fails, the ingest still loads the files that exist
  And the heartbeat posts {"ok": false, "failed": ["capture"]}
  And, with SENTRY_DSN set, Sentry receives the exception without frame locals

Scenario: nothing captured
  Given no capture file exists after the capture step
  Then the ingest step prints "No capture files to ingest" and fails
  And the heartbeat reports "ingest" as failed
```

## Out of scope

Application prep, sending, the Windows/local scheduler, property and Facebook
lanes. They run only on the owner's machine (see `RUNBOOK.md`).
