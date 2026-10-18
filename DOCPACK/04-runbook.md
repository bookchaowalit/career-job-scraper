---
title: Book Job Scraping — Runbook การติดตั้งและดูแลระบบ
doc_id: BJS-DOC-04
doc_type: runbook
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Operator / DevOps (Book Dev)
related: 02-architecture.md, 03-nfr-security.md, 06-ux-flows.md, 07-test-uat.md
---

# Book Job Scraping — Runbook การติดตั้งและดูแลระบบ

> สรุปจาก `RUNBOOK.md`, `README.md`, `SAFETY.md` และ `CAREER-WORKFLOW.md` ถ้าขัดกัน ให้ `SAFETY.md` มีผลเหนือกว่า

## 1. Environments

| Env | ใช้ทำอะไร | สถานะ |
|---|---|---|
| Windows host ของ operator | scheduler หลัก (`ops/windows/scheduled-task.ps1`) | ใช้งานตั้งแต่ 2026-09-30 |
| Linux | `setup_cron.sh` (ความหมายเดียวกัน) | สำรอง |
| CI | Ubuntu (ruff + pytest) และ Windows (scheduler tests) | ใช้งาน |
| Production server | ไม่มี | — |

## 2. ติดตั้ง / build

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # เฉพาะ job ที่ต้อง render JS
.venv/bin/python scripts/pipeline_runner.py --dry-run
```

ไม่มีขั้น build; สคริปต์ห้าม `pip install` ระหว่างรัน

## 3. Config (ชื่อตัวแปรเท่านั้น)

| กลุ่ม | ตัวแปร |
|---|---|
| Path | `BOOK_JOB_SCRAPING_ROOT`, `PIPELINE_DATA_DIR`, `BOOK_JOB_SCRAPING_DATA_DIR` (ฝั่ง `book-job-data`) |
| Health | `PIPELINE_HEALTH_MODE`, `PIPELINE_COLLECTION_MAX_AGE_HOURS`, `PIPELINE_REQUIRE_OPENROUTER`, `PIPELINE_REQUIRE_TELEGRAM` |
| Politeness | `JOB_SCRAPE_MIN_INTERVAL` |
| Capture | `FIRECRAWL_API_KEY`, `JINA_API_KEY` |
| AI (ทางเลือก) | `OPENROUTER_API_KEY`, `AI_MODEL` |
| แจ้งเตือน (ทางเลือก) | `TELEGRAM_NOTI_BOT_TOKEN` (`book_noti_bot`) หรือ `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Send gate (ห้ามตั้งโดยไม่มีคำสั่ง) | `BOOK_JOB_LIVE_SEND_ENABLED`, `BOOK_JOB_SEND_UNLOCK` |
| Social/property gate (ค่าเริ่มต้นปิด) | `BRAVE_SEARCH_API_KEY`, `BRAVE_SEARCH_STORAGE_APPROVED`, `PROPERTY_SOCIAL_RETENTION_UNTIL`, `PROPERTY_SOCIAL_TERMS_BASIS_REF`, `TGCONDO_CONTACT_STORAGE_APPROVED`, `TGCONDO_RETENTION_UNTIL`, `TGCONDO_TERMS_BASIS_REF` |
| Integration อื่นในสคริปต์ | `GITHUB_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `LEANTIME_URL`, `LEANTIME_API_KEY` **[ต้องยืนยัน]** ว่ายังใช้ |

ค่าจริงอยู่ใน secret store ส่วนตัว; ห้าม commit `.env`, tracker CSV, browser profile หรือ PII

## 4. รันและติดตั้ง scheduler

```bash
.venv/bin/python main.py run                 # รัน job ที่ถึงเวลา
.venv/bin/python main.py run job_postings    # รัน job เดียว
.venv/bin/python main.py status
bash setup_cron.sh install | status | remove  # Linux
.\ops\windows\scheduled-task.ps1 install      # Windows (PowerShell)
```

Windows: ตั้ง `PYTHONUTF8=1` เมื่อรันเอง (scheduled runner ตั้งให้แล้ว)

## 5. Health check

```bash
.venv/bin/python scripts/pipeline_runner.py --health
.venv/bin/python scripts/pipeline_health_monitor.py
.venv/bin/python scripts/source_coverage.py --check
```

เขียว = `job_postings.csv`, `matched_jobs.csv`, `apply_tracker.csv`, `job_descriptions.csv` สดทั้งหมด

## 6. Rollback

1. หยุด scheduler ของ repo นี้: `bash setup_cron.sh remove` หรือ uninstall task บน Windows **[ต้องยืนยัน]** คำสั่ง uninstall ของ `scheduled-task.ps1`
2. เก็บ `data/` ไว้ตรวจ ห้ามลบ
3. ถอย commit ที่มีปัญหาแล้วรัน `pytest -q`
4. ปิด job ที่เสียด้วย `main.py disable <job>` แทนการแก้ด่วน
5. ห้ามเปิด live send/apply ระหว่าง rollback

## 7. Incident / troubleshooting

| อาการ | ตรวจ | แก้ |
|---|---|---|
| Health แดง: artifact เก่า | `main.py status`, `cron.log` | รัน `main.py run job_postings` เอง; ดู error ของบอร์ด |
| บอร์ดตอบ 403/Cloudflare | log ของ job | disable job; บันทึกใน `config/source_coverage.yaml` |
| Tick ไม่รัน | lock ค้าง | ตรวจว่ามี process ค้าง; tick ใหม่จะข้ามถ้ายังถือ lock |
| Tick exit 124 | step เกิน timeout | ดู job ที่ช้า ลด scope หรือ disable |
| `Missing dependency` | venv ไม่ครบ | `pip install -r requirements.txt` ใน `.venv` |
| JSON store อ่านไม่ได้ | ไฟล์เสีย | ระบบเก็บไฟล์เดิมไว้ไม่ทับ (fix 2026-09-30); ตรวจแล้วกู้เอง |

## 8. Backup / restore

- ไฟล์สำคัญ: `data/confirmed_applications.json`, `data/career-review/`, `data/apply_tracker.csv`, `config/`
- มี `scripts/pipeline_backup.py` / `pipeline_recovery.py` **[ต้องยืนยัน]** วิธีใช้และปลายทาง
- Restore: คัดลอกกลับ `data/` แล้วรัน health check; receipt ที่ import เข้า JOB-TRACKER แล้วยังอยู่ใน Solo Empire

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Operator (Book Dev) | รอตรวจ | — | [ต้องยืนยัน] |

## แหล่งข้อมูล

- `RUNBOOK.md`, `README.md` (Quick Start, Collection health), `SAFETY.md`, `CAREER-WORKFLOW.md`
- `main.py`, `setup_cron.sh`, `ops/windows/scheduled-task.ps1`, `scripts/` (env var names จากการค้นในโค้ด)
