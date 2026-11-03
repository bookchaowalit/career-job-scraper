# 06 — C4 Container

"Container" ที่นี่คือหน่วยที่รันแยกกันจริง: workflow บน GitHub Actions, process Python บนเครื่อง operator, Chrome extension, Apps Script และ data directory

```mermaid
C4Container
  title career-job-scraper - Containers
  Person(op, "Operator / Owner")

  System_Boundary(sys, "career-job-scraper") {
    Container(cap, "Hosted capture job", "GitHub Actions ubuntu-24.04, Python 3.11, uv", "scheduled-capture.yml + scripts/cloud_capture.py")
    Container(tick, "Local scheduler tick", "Python, Windows Task Scheduler or cron", "scripts/scheduled_run.py -> main.py run -> pipeline_health_monitor.py")
    Container(cli, "Operator CLI scripts", "Python scripts/", "application_review, importers, reviewers, dashboards, gated senders")
    Container(mcp, "MCP server", "Python mcp_server/server.py", "search_jobs, search_businesses, get_product_prices, get_news")
    Container(ext, "Quick Saver extension", "Chrome MV3 JS 1.5.0", "Save job pages, property rows, FB Group posts; CSV export")
    Container(gas, "Sheet receiver", "Google Apps Script web app", "integrations/google-sheet/Code.gs doPost to raw_posts")
    ContainerDb(data, "data/ directory", "CSV and JSON files, gitignored", "job_postings.csv, matched_jobs.csv, apply_tracker.csv, career-review/, schedule_state.json")
    ContainerDb(cache, "Actions cache", "GitHub cache", "data/job_postings_history.csv only")
  }

  System_Ext(boards, "Job boards + Greenhouse")
  System_Ext(bjd, "book-job-data ingest CLI")
  System_Ext(r2, "Cloudflare R2")
  System_Ext(mon, "Uptime Worker heartbeat")
  System_Ext(sentry, "Sentry")
  System_Ext(clouds, "Drive / Dropbox / OneDrive")

  Rel(cap, boards, "HTTP GET")
  Rel(cap, cache, "Restore and save history")
  Rel(cap, bjd, "--input job_postings.csv, matched_jobs.csv")
  Rel(bjd, r2, "Write lake datasets")
  Rel(cap, mon, "POST /heartbeat/job-capture")
  Rel(cap, sentry, "Errors")
  Rel(tick, boards, "HTTP GET")
  Rel(tick, data, "Read and write CSV, JSON")
  Rel(cli, data, "Read matches, write packets and ledger")
  Rel(mcp, data, "Read data/<collection>/items.json")
  Rel(op, ext, "Clicks save, capture, export")
  Rel(ext, gas, "POST public rows with SECRET")
  Rel(ext, clouds, "Upload exported CSV, opt-in")
  Rel(op, cli, "Runs")
```

Sources: `.github/workflows/scheduled-capture.yml`, `scripts/cloud_capture.py`, `scripts/scheduled_run.py`, `main.py`, `mcp_server/server.py`, `chrome-extension/manifest.json`, `chrome-extension/sheet.js`, `chrome-extension/cloud.js`, `integrations/google-sheet/Code.gs`, `adapters/outbound/storage_adapter.py`, `DOCPACK/02-architecture.md` §4

หมายเหตุ: hosted capture ไม่ได้เขียน `data/` ถาวร: runner ทิ้งไฟล์ทุก run เหลือเฉพาะ history ใน Actions cache

## Open questions

- ระบบ `scripts/scrape_facebook_group_background.py` (Playwright opt-in) และ `ops/systemd/facebook-group-background.*.example` เป็น container ที่ถูก install จริงบนเครื่องไหนหรือไม่ (ไฟล์เป็น `.example`)
