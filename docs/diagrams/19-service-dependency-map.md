# 19 — Service dependency map

runtime dependency ของแต่ละ runtime; เส้นทึบ = ต้องมีเพื่อให้ผลหลักสำเร็จ, เส้นประ = optional / opt-in

```mermaid
flowchart TD
  subgraph CAP["Hosted capture"]
    CC["cloud_capture.py"]
  end
  subgraph TICK["Local tick"]
    MR["main.py run + health monitor"]
  end

  GHA["GitHub Actions: schedule, runner, cache, secrets"] --> CC
  PYPI["PyPI via uv.lock"] --> CC
  BJDSRC["GitHub tarball career-job-market-data at BOOK_JOB_DATA_REF"] --> CC
  CC --> BOARDS["Remote job boards"]
  CC --> GH["Greenhouse boards-api"]
  CC --> R2["Cloudflare R2 S3 API"]
  CC --> UW["Cloudflare Worker solo-empire-monitor"]
  CC -.-> SEN["Sentry"]
  R2 --> API["Railway book-job-data-api"]
  UW --> TGA["Telegram alert to owner"]

  WIN["Windows Task Scheduler or cron"] --> MR
  MR --> BOARDS
  MR --> GH
  MR --> FEEDS["GitHub API, HN, dev.to, Product Hunt"]
  MR --> FC["Firecrawl API"]
  MR -.-> TG["Telegram Bot API"]
  MR -.-> OR["OpenRouter, optional enrichment"]
  MR --> DISK[("Local data/")]

  EXT["Chrome extension"] -.-> GOOG["Google Drive, Apps Script"]
  EXT -.-> DBX["Dropbox"]
  EXT -.-> MS["Microsoft Graph OneDrive"]
```

| Dependency | Failure effect | Handling in code |
|---|---|---|
| A board host down | fewer postings that run | `PoliteHttp` retry + circuit breaker per host; other boards continue |
| Greenhouse board fails | career_postings not overwritten | `career_discovery` keeps previous capture when any board fails (`DOCPACK/05-srs.md` US-03) |
| One cloud job raises | run exit 1, later jobs still run | `cloud_capture.run()` |
| R2 / ingest fails | data stale in API | step fails → heartbeat `failed: [ingest]` |
| Uptime Worker unreachable | no alert | `curl -fsS` fails the Heartbeat step only |
| Sentry unreachable | errors not reported | `flush(5)`; run result unaffected |
| GitHub schedule delayed / disabled after 60 days idle | freshness drops | heartbeat silence alert > 13 h |

Sources: `.github/workflows/scheduled-capture.yml`, `scripts/cloud_capture.py`, `scripts/http_policy.py`, `scripts/career_discovery.py`, `scripts/_sentry.py`, `scripts/scheduled_run.py`, `config/jobs.yaml`, `chrome-extension/manifest.json`, `RUNBOOK.md` §Configure, §Hosted job capture

## Open questions

- OpenRouter ใช้จากสคริปต์ใดใน path ที่ schedule จริง (RUNBOOK ระบุเป็น optional enrichment เท่านั้น)
