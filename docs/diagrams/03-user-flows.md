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
  D --> F{"10 or more saved rows?"}
  F -->|"yes"| G["exportToCSV: writes lastExport to chrome.storage.local only"]
  F -->|"no"| H["Stay local"]
  G --> H
```

Sources: `chrome-extension/manifest.json`, `chrome-extension/background.js` (`saveJob` / `quickSave` → `exportToCSV()`; `cloud.uploadExport()` is called only for property and Facebook exports, lines 148 and 448), `chrome-extension/popup.js`, `chrome-extension/cloud.js`

หมายเหตุ: job ที่บันทึกไม่ถูก upload ขึ้น cloud แม้เปิด cloud upload ไว้ — ข้อมูล job อยู่ในเครื่องเท่านั้น

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
  G -->|"no"| I["No Sheet send"]
  F --> CU{"Cloud auto-upload enabled?"}
  CU -->|"yes"| CU1["cloud.uploadExport: full CSV incl. private and unknown rows to own Drive, Dropbox or OneDrive"]
  CU -->|"no"| CU2["CSV download only, stays on this machine"]
  F --> J["import_facebook_group_posts.py offline"]
  J --> K{"visibility public and has text?"}
  K -->|"no"| L["Quarantine row"]
  K -->|"yes"| K2{"text_complete?"}
  K2 -->|"yes"| M["Review queue: review_decision pending, outreach not_contacted"]
  K2 -->|"no"| M2["Accepted with lead_review_status needs_human_review"]
  M2 --> M
  M --> N["review_facebook_group_posts.py with reviewer ID"]
```

Sources: `chrome-extension/popup.js`, `chrome-extension/background.js`, `chrome-extension/sheet.js`, `integrations/google-sheet/Code.gs`, `scripts/import_facebook_group_posts.py`, `scripts/review_facebook_group_posts.py`, `contracts/facebook-group-post.v1.json`, `SAFETY.md`

## Open questions

- `DOCPACK/06-ux-flows.md` 2.1 เขียนว่า "Scheduler เก็บงาน ทุก 6 ชม." แต่ local tick ทุก 5 นาทีและ job ถึงเวลาตาม `is_due()` (6h): ถูกต้องในแง่ job แต่ควรระบุว่ามีสอง scheduler
- Popup นับ `applied` จาก stats ของ extension: ค่านี้สัมพันธ์กับสถานะ `submitted` ใน ledger หรือไม่
