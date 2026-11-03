# 02 — Use cases

ไม่มีระบบ login; "บทบาท" มาจากการเข้าถึงเครื่อง, env และ flag บน CLI (`DOCPACK/05-srs.md` §1)
actor ด้านล่างคือบทบาทที่โค้ดแยกสิทธิ์จริง:

| Actor | กลไกในโค้ด |
|---|---|
| GitHub Actions scheduler | `scheduled-capture.yml` cron + secrets R2/heartbeat/Sentry |
| Local scheduler | `scheduled_run.py` จาก Task Scheduler / cron |
| Operator | รันสคริปต์ใน `scripts/`, Chrome extension, MCP |
| Owner (approver) | `prepare --owner-approved`, env `BOOK_JOB_LIVE_SEND_ENABLED=1` + `BOOK_JOB_SEND_UNLOCK` |
| Reviewer (property / FB lane) | `review_property_leads.py`, `review_facebook_group_posts.py` ต้องมี reviewer ID |
| AI agent | `mcp_server/server.py` tools |
| book-job-data (ระบบภายนอก) | อ่าน CSV, เขียน R2 |

```mermaid
flowchart LR
  GHA(["GitHub Actions scheduler"])
  LS(["Local scheduler"])
  OP(["Operator"])
  OW(["Owner approver"])
  RV(["Reviewer"])
  AI(["AI agent via MCP"])
  BJD(["book-job-data ingest"])

  subgraph SYS["career-job-scraper"]
    UC1(("Capture remote job boards"))
    UC2(("Capture Greenhouse career boards"))
    UC3(("Classify matches PASS / VERIFY / REJECT"))
    UC4(("Publish capture to R2"))
    UC5(("Check collection health"))
    UC6(("Build review packet"))
    UC7(("Prepare application packet"))
    UC8(("Approve packet"))
    UC9(("Record manual submission"))
    UC10(("Live send or ATS apply, gated"))
    UC11(("Capture page or FB Group posts with extension"))
    UC12(("Import and review property or FB rows"))
    UC13(("Search stored data"))
    UC14(("Capture discovery feeds and dashboard"))
  end

  GHA --> UC1
  GHA --> UC2
  GHA --> UC3
  GHA --> UC4
  BJD --> UC4
  LS --> UC1
  LS --> UC2
  LS --> UC3
  LS --> UC5
  LS --> UC14
  OP --> UC5
  OP --> UC6
  OP --> UC7
  OP --> UC9
  OP --> UC11
  OP --> UC12
  OW --> UC8
  OW --> UC10
  RV --> UC12
  AI --> UC13
```

Sources: `.github/workflows/scheduled-capture.yml`, `scripts/cloud_capture.py`, `scripts/scheduled_run.py`, `config/jobs.yaml`, `scripts/application_review.py`, `scripts/safety.py`, `SAFETY.md`, `chrome-extension/manifest.json`, `scripts/import_property_leads.py`, `scripts/import_facebook_group_posts.py`, `scripts/review_property_leads.py`, `scripts/review_facebook_group_posts.py`, `mcp_server/server.py`, `DOCPACK/05-srs.md`

หมายเหตุ: UC10 (live send/apply) มีโค้ดอยู่ (`send_application_emails.py`, `ats_auto_apply.py` ฯลฯ) แต่ล็อกโดยค่าเริ่มต้น ต้องผ่าน flag + 2 env + `PASS` + `APPROVED` (`SAFETY.md`)

## Open questions

- MCP server (`mcp_server/server.py` `main()`) แค่พิมพ์รายการ tool และบอกให้ "integrate with MCP SDK": ยังไม่มี transport จริง ใช้งานจาก agent ได้จริงหรือไม่
- Reviewer เป็นคนเดียวกับ owner หรือไม่ (solo operator ตาม `RUNBOOK.md` §Owner)
