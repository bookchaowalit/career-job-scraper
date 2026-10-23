---
title: BJS — KPI and Instrumentation Plan (hosted capture, Track B)
created: 2026-10-23
updated: 2026-10-23
status: draft
template: architecture-docs templates/sdlc/kpi-and-instrumentation-plan.md
related: [../../specs/cloud-capture-pipeline.md, ../../RUNBOOK.md, ../../DOCPACK/05-srs.md]
---

# BJS — KPI and Instrumentation Plan

Scope: the hosted capture of the job system (Track B), i.e.
`.github/workflows/scheduled-capture.yml` → `scripts/cloud_capture.py` →
`book-job-data` ingest into R2. The local scheduler and the application-prep
pipeline are out of scope here; they have no hosted runtime to measure.

This is a personal tool with no external users, so there are no product
analytics events and no personal data in any metric. Every KPI below comes
from data the system already writes (Actions run records, the public
counts-only log, the heartbeat, the R2 dataset read by `book-job-data-api`).

## Document control

| Field | Value |
|---|---|
| Project / product ID | BJS (DOCPACK prefix; system `book-apps/tools/book-job-scraping`, repo `career-job-scraper`) |
| Version | 0.1 |
| Status | draft — KPIs defined, partly instrumented (see "Status" column) |
| Metric owner | Owner (solo) |
| AI maker | Claude Code (Big Loop code-gaps batch, 2026-10-23) |
| AI reviewer | Not yet reviewed by a second agent |
| Objectives | OBJ-01 fresh job postings in the lake for matching; OBJ-02 the hosted run stays cheap and quiet (no private data, no alert noise) |
| Data source of truth | GitHub Actions run history + run logs of `scheduled-capture.yml`; R2 `portfolio-demo/book-job-data-001` via `book-job-data-api` `GET /v1/metadata` |
| Dashboard | None yet. Uptime Worker heartbeat `job-capture` is the only alerting surface |
| Next review | 2026-11-23 |

## KPI tree

```text
OBJ-01 Fresh job postings in the lake for matching
  └─ KPI-O-01 Capture freshness (age of newest ingested capture)
       ├─ KPI-L-01 Postings captured per run (job_postings + career_postings)
       ├─ KPI-L-02 New postings per run (job_postings new=)
       ├─ KPI-L-03 Match-filter output per run (matched_jobs records)
       └─ KPI-G-01 Run failure rate
OBJ-02 Hosted run stays cheap and private
  └─ KPI-G-02 Private data in the public log (must stay 0)
  └─ KPI-G-03 Run duration (GitHub-hosted minutes)
```

## KPI definitions

| KPI ID | Type | Name | Formula | Unit | Min volume | Data source (where measured today) | Baseline (value, period, evidence) | Target | Alert threshold | Cadence | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| KPI-O-01 | outcome | Capture freshness | now − finish time of the newest successful run that ingested ≥ 1 file | hours | n/a | Actions run history (`gh run list --workflow scheduled-capture.yml`); `GET /v1/metadata` `data_status` on `book-job-data-api` | Max gap between successful runs 7.3 h (8 runs, 2026-10-21 → 2026-10-23; GitHub starts the `:17` schedule 25–45 min late) | ≤ 8 h at any time, judged 2026-11-23 | Heartbeat silence > 13 h (uptime Worker `job-capture`) | continuous | instrumented (heartbeat alert); not charted |
| KPI-L-01 | leading | Postings captured per run | `job_postings scraped=` + `career_postings scraped=` | postings | n/a | Public Actions log, one line per job from `cloud_capture.run()` | 536–601 per run (job_postings 388–453, career_postings 148), same 8 runs | ≥ 450 per run, judged 2026-11-23 | none yet | per run | logged only; no aggregation or alert |
| KPI-L-02 | leading | New postings per run | `job_postings new=` (vs `data/job_postings_history.csv` carried in the Actions cache) | postings | n/a | Public Actions log | 8–123 per run after the first run (first run 435, empty history) | > 0 on ≥ 3 of 4 daily runs | none yet | per run | logged only |
| KPI-L-03 | leading | Match-filter output per run | `job_match_filter scraped=` (rows written to `matched_jobs.csv`, statuses PASS + VERIFY, min_score 5) | postings | n/a | Public Actions log; ingest log `"records"` for `matched_jobs.csv` | 157–161 per run, same 8 runs | 50–300 per run (outside = policy or source drift) | none yet | per run | logged only |
| KPI-G-01 | guardrail | Run failure rate | failed runs / all runs of `scheduled-capture.yml` (a run fails if any job or the ingest fails) | % | ≥ 20 runs (5 days); below that report "not measurable" | Actions run conclusions; per-job failures in Sentry once `SENTRY_DSN` is set | 0 / 8 (not measurable yet: under 20 runs) | ≤ 5% over 30 days | Any failed run → heartbeat posts `ok:false` → Telegram at once | daily | instrumented (heartbeat + Sentry per job) |
| KPI-G-02 | guardrail | Private data in the public log | runs whose public log shows anything other than counts, status lines and dataset names | runs | n/a | `tests/test_cloud_capture.py` (output goes to the private log file); manual review of one run log per change | 0 (reviewed run 39948237939, 2026-10-23) | 0, always | any non-zero | per change | enforced by tests; manual log review |
| KPI-G-03 | guardrail | Run duration | Actions run duration | minutes | n/a | Actions run history | 2 m 45 s – 3 m 59 s, same 8 runs | ≤ 10 min (job timeout 30 min) | none yet | weekly | visible in Actions; no alert |

Rules from the template apply: below the minimum volume a rate is "not
measurable"; a KPI without a baseline cannot back a benefit claim.

## Event and data specification

No analytics events. The "events" are system records that already exist:

| Record | Trigger | Properties | Personal data? | Emitted by | Requirement | Status |
|---|---|---|---|---|---|---|
| Job status line `<job>: ok scraped=N new=M` / `<job>: failed: <error ≤ 200 chars>` | Each cloud job finishes | job name, counts, truncated error | no | `scripts/cloud_capture.py` | SPEC-CAP-04 | implemented |
| Ingest summary (`"captures"`, `"records"`) | `book-job-data` ingest finishes | dataset, record count | no | `book-job-data` CLI | SPEC-CAP-06 | implemented |
| Heartbeat `{ok, failed[]}` | Every run (`always()`) | failed step names | no | workflow step `Heartbeat` | SPEC-CAP-07 | implemented |
| Sentry error event | Exception or failed result in a cloud job | exception type, scrubbed message, frames without locals, tag `job` | no (allowlist scrub, `send_default_pii=False`) | `scripts/_sentry.py` | SPEC-CAP-08 | implemented (`SENTRY_DSN` repo secret set 2026-10-23) |

Privacy: job postings are public; the private `apply_tracker.csv` never exists
on the runner (`seed_tracker: false`). Retention: Actions logs follow the
GitHub default (90 days); Sentry free plan retention applies to error events.

## Dashboards and alerts

| Dashboard / alert | KPIs | Location | Alert channel | Status |
|---|---|---|---|---|
| Uptime Worker heartbeat `job-capture` | KPI-O-01, KPI-G-01 | `solo-empire-monitor` Worker | Telegram (owner) | live |
| Sentry project `career-job-scraper` | KPI-G-01 (per job) | Sentry org `personal-yu0` | Sentry email (default alert rule) | live from 2026-10-23 (`SENTRY_DSN` repo secret set) |
| Per-run counts chart (KPI-L-01..03) | KPI-L-01, L-02, L-03 | — | — | not instrumented: counts exist only in run logs; a parser over `gh run view --log` or a metrics row written by the ingest is the next step |

## Instrumentation verification

| # | Check | Evidence | Result |
|---|---|---|---|
| 1 | Status lines appear once per job per run | Run 39948237939 log | pass |
| 2 | Ingest record counts reconcile with match output (157 = 157) | Same run | pass |
| 3 | No private data in the public log | Same run; `tests/test_cloud_capture.py` | pass |
| 4 | Dashboard renders each KPI | — | fail: no dashboard for L-01..03 |
| 5 | Heartbeat alert fires on a failure | Not tested in this change | open |
| 6 | Baselines captured | This file, 8 runs | pass (KPI-G-01 not measurable until 20 runs) |
| 7 | Consent | Not applicable: no user tracking | n/a |

## Change history of definitions

| Date | KPI ID | Change | Reason | Baseline restated? | Approved by |
|---|---|---|---|---|---|
| 2026-10-23 | all | First version | Big Loop L3 | n/a | pending owner |
