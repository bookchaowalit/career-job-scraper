# 10 — Sequences

ลำดับ tick ของ local scheduler มีอยู่แล้วใน [`DOCPACK/02-architecture.md`](../../DOCPACK/02-architecture.md) §5.1 (reused)
ไฟล์นี้เพิ่ม 3 path สำคัญ: hosted capture run, การ execute job หนึ่งตัว และ record-submission

## 1. Hosted capture run (GitHub Actions)

```mermaid
sequenceDiagram
  participant GH as GitHub schedule
  participant WF as scheduled-capture.yml
  participant CC as cloud_capture.py
  participant M as main.execute_job
  participant B as Job boards and Greenhouse
  participant S as Sentry
  participant I as book-job-data CLI
  participant R2 as Cloudflare R2
  participant HB as Uptime Worker
  GH->>WF: cron 17 */6 * * *
  WF->>WF: restore job_postings_history.csv cache
  WF->>CC: python scripts/cloud_capture.py
  loop job_postings, career_postings, job_match_filter
    CC->>M: execute(job) with output redirected to private log
    M->>B: HTTP GET via polite client
    B-->>M: postings
    M-->>CC: result scraped, new
    alt failed or exception
      CC->>S: capture_exception or capture_failure
      CC-->>WF: print job failed line
    else success
      CC-->>WF: print job ok scraped=N new=M
    end
  end
  WF->>WF: save history cache
  WF->>CC: --inputs
  CC-->>WF: existing job_postings.csv, matched_jobs.csv
  WF->>I: book-job-data --input ... --data-lake-uri
  I->>R2: write datasets
  I-->>WF: dataset names and record counts
  WF->>HB: POST /heartbeat/job-capture ok, failed
```

Sources: `.github/workflows/scheduled-capture.yml`, `scripts/cloud_capture.py`, `scripts/_sentry.py`, `main.py`, `scripts/http_policy.py`

## 2. Execute one configured job (main.py)

```mermaid
sequenceDiagram
  participant C as caller main.py run or cloud_capture
  participant SA as SchedulerAdapter
  participant L as load_category_scraper
  participant SC as Scraper class from scraper_module
  participant UC as ScrapeUseCase
  participant ST as data/schedule_state.json
  C->>SA: get_pending_jobs or jobs[name]
  SA-->>C: ScrapeJob
  C->>L: job.scraper_module, job.scraper_class
  alt module configured
    L->>SC: construct with job.params and rate_limit
    C->>SC: await run(max_pages)
    SC-->>C: rows or count/new dicts
  else no module
    C->>UC: execute(job): scrape, clean, dedup, export, save
    UC-->>C: ScrapeResult
  end
  C->>SA: mark_completed(job, result)
  SA->>ST: write_json_atomic last_run, run_count, error_count
```

Sources: `main.py`, `adapters/inbound/scheduler_adapter.py`, `core/use_cases.py`, `core/atomic_io.py`

## 3. Record a manual submission

```mermaid
sequenceDiagram
  participant O as Operator
  participant AR as application_review.py
  participant P as prepared.json
  participant Q as job_target_policy
  participant LG as confirmed_applications.json
  participant JT as Solo Empire importer
  O->>AR: record-submission manifest, receipt, submitted_at
  AR->>P: read packet
  AR->>AR: require owner_approved true and status prepared
  AR->>AR: re-hash candidate, verification, resume, cover letter
  AR->>Q: qualify_job(packet.job)
  Q-->>AR: PASS required
  AR->>AR: check submitted_at has offset, not future, not before created_at, receipt non-empty
  AR->>LG: exclusive_lock, dedup by canonical url
  AR->>LG: atomic write entry status submitted, followup_date +7 days
  O->>JT: import_job_applications.py --input confirmed_applications.json
```

Sources: `scripts/application_review.py` (`record_submission`), `scripts/job_target_policy.py`, `scripts/file_lock.py`, `CAREER-WORKFLOW.md`

## Open questions

- ไม่มี sequence ของ ingest ภายใน `book-job-data` ในที่นี้ (อยู่ใน repo `career-job-market-data`)
