# 03 — User flows

**Reused:** flow หลักของ operator มีอยู่แล้วใน [`DOCPACK/06-ux-flows.md`](../../DOCPACK/06-ux-flows.md)
(2.1 จากประกาศงานถึงใบสมัครที่มีหลักฐาน, 2.2 gate ของ sender, 2.3 health รายวัน และ screen inventory SC-01..SC-10)
ไฟล์นี้เพิ่มเฉพาะ flow ที่ยังไม่มีในเอกสารเดิม: hosted capture (ไม่มีมนุษย์), Chrome extension และ property/FB review

ไม่มี web route หรือ page; "หน้าจอ" คือ CLI, ไฟล์ review packet, popup ของ extension และ MCP tools

## Flow A — Hosted capture (ไม่มี operator)

```mermaid
flowchart TD
  A["Cron 17 */6 * * * UTC or workflow_dispatch"] --> B["uv sync --frozen --no-dev"]
  B --> C["Install book-job-data at BOOK_JOB_DATA_REF"]
  C --> D["Restore data/job_postings_history.csv from Actions cache"]
  D --> E["cloud_capture.py: 3 jobs, one status line each"]
  E --> F["Save history cache"]
  F --> G{"Any capture file exists?"}
  G -->|"no"| H["Print No capture files to ingest, step fails"]
  G -->|"yes"| I["book-job-data ingest to R2"]
  H --> J["Heartbeat job-capture with failed steps"]
  I --> J
```

Sources: `.github/workflows/scheduled-capture.yml`, `scripts/cloud_capture.py`, `specs/cloud-capture-pipeline.md`

## Flow B — Operator: save a job page with Quick Saver

```mermaid
flowchart TD
  A["Operator opens a job page on a listed board"] --> B["content.js runs on host_permissions boards"]
  B --> C{"Popup Save or context menu?"}
  C -->|"saveJob / quickSave"| D["background.js stores row in chrome.storage.local savedJobs"]
  D --> E["Popup stats: today saved, total, applied"]
  E --> F{"Cloud upload enabled in options?"}
  F -->|"no, default"| G["Stay local"]
  F -->|"yes"| H["Upload exported CSV to own Drive, Dropbox or OneDrive"]
```

Sources: `chrome-extension/manifest.json`, `chrome-extension/background.js`, `chrome-extension/popup.js`, `chrome-extension/cloud.js`

## Flow C — Operator: Facebook Group posts to review queue

```mermaid
flowchart TD
  A["Operator opens a Group tab and the popup"] --> B["Capture visible posts or start Auto-scroll capture"]
  B --> C["Auto-scroll: one screen per step, 4 s wait, stop at 40 posts or 5 min by default"]
  C --> D["writeCaptureDraft: facebookGroupCaptureDraft in local storage"]
  B --> D
  D --> E["Operator labels visibility public, private or unknown"]
  E --> F["Save or Export CSV"]
  F --> G{"Sheet sink enabled?"}
  G -->|"yes"| H["Send only public rows to own Apps Script web app"]
  G -->|"no"| I["CSV download only"]
  F --> J["import_facebook_group_posts.py offline"]
  J --> K{"public and complete?"}
  K -->|"no"| L["Quarantine row"]
  K -->|"yes"| M["Review queue: review_decision pending, outreach not_contacted"]
  M --> N["review_facebook_group_posts.py with reviewer ID"]
```

Sources: `chrome-extension/popup.js`, `chrome-extension/background.js`, `chrome-extension/sheet.js`, `integrations/google-sheet/Code.gs`, `scripts/import_facebook_group_posts.py`, `scripts/review_facebook_group_posts.py`, `contracts/facebook-group-post.v1.json`, `SAFETY.md`

## Open questions

- `DOCPACK/06-ux-flows.md` 2.1 เขียนว่า "Scheduler เก็บงาน ทุก 6 ชม." แต่ local tick ทุก 5 นาทีและ job ถึงเวลาตาม `is_due()` (6h): ถูกต้องในแง่ job แต่ควรระบุว่ามีสอง scheduler
- Popup นับ `applied` จาก stats ของ extension: ค่านี้สัมพันธ์กับสถานะ `submitted` ใน ledger หรือไม่
