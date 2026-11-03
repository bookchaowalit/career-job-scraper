# 05 — C4 Context

ภาพระดับระบบ: career-job-scraper เป็น producer ที่ดึงประกาศงานสาธารณะและส่งไฟล์ CSV ให้ `book-job-data`
บริบทเดิมแบบ flowchart อยู่ใน [`DOCPACK/02-architecture.md`](../../DOCPACK/02-architecture.md) §1 (บอร์ดในภาพเดิมบางตัว เช่น Dice, Wellfound ไม่อยู่ใน `boards` ของ `job_postings` แล้ว)

```mermaid
C4Context
  title career-job-scraper - System Context
  Person(op, "Operator / Owner", "Solo operator: runs scripts, reviews and approves applications")
  System(cjs, "career-job-scraper", "Job discovery capture, match filter, application prep tooling")
  System_Ext(boards, "Remote job boards", "Remotive, WWR, RemoteOK, Himalayas, Jobicy, HN hiring, Working Nomads, The Muse, Arc, Fastwork, PeoplePerHour")
  System_Ext(gh, "Greenhouse Job Board API", "boards-api.greenhouse.io public GET")
  System_Ext(feeds, "Discovery feeds", "GitHub search API, HN Firebase API, dev.to API, Product Hunt feed")
  System_Ext(fc, "Firecrawl API", "Search for property_listings")
  System_Ext(bjd, "book-job-data", "Ingest CLI and Railway book-job-data-api")
  System_Ext(r2, "Cloudflare R2", "Lake prefix portfolio-demo/book-job-data-001")
  System_Ext(mon, "solo-empire-monitor Worker", "Heartbeat job-capture, Telegram alert")
  System_Ext(sentry, "Sentry", "Project career-job-scraper, errors only")
  System_Ext(tg, "Telegram Bot API", "Optional local notifications")
  System_Ext(cloud, "Operator cloud storage", "Google Drive, Dropbox, OneDrive, Apps Script Sheet")
  System_Ext(tracker, "Solo Empire JOB-TRACKER", "Confirmed applications record")
  System_Ext(ats, "Company ATS sites", "Manual submission by operator")

  Rel(op, cjs, "Runs CLI, extension, review")
  Rel(cjs, boards, "HTTP GET with rate limit and retry")
  Rel(cjs, gh, "HTTP GET")
  Rel(cjs, feeds, "HTTP GET, local scheduler only")
  Rel(cjs, fc, "HTTPS API, FIRECRAWL_API_KEY")
  Rel(cjs, bjd, "CSV files as ingest input")
  Rel(bjd, r2, "Writes datasets")
  Rel(cjs, mon, "POST heartbeat every hosted run")
  Rel(cjs, sentry, "Error events when SENTRY_DSN set")
  Rel(cjs, tg, "Optional sendMessage")
  Rel(cjs, cloud, "Extension uploads exported CSV, opt-in")
  Rel(cjs, tracker, "confirmed_applications.json via importer")
  Rel(op, ats, "Submits applications by hand")
```

Sources: `config/jobs.yaml`, `config/career_sources.yaml`, `scripts/scrape_job_postings.py`, `scripts/career_discovery.py`, `scripts/scrape_property_listings.py`, `.github/workflows/scheduled-capture.yml`, `scripts/_sentry.py`, `scripts/pipeline_health_monitor.py`, `chrome-extension/cloud.js`, `chrome-extension/sheet.js`, `integrations/google-sheet/Code.gs`, `CAREER-WORKFLOW.md`, `PRODUCT.md`

## Open questions

- Railway `job-radar` (Track A) alert บนบอร์ดเดียวกัน แต่เป็นระบบแยก ไม่ได้เรียกจาก repo นี้ (`specs/cloud-capture-pipeline.md` §Context): ควรอยู่ในภาพ context หรือไม่
