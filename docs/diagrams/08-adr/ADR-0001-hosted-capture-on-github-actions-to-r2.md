# ADR-0001 — Hosted capture บน GitHub Actions แล้ว publish เข้า R2 ผ่าน book-job-data

- **Status:** accepted (retro-documented)
- **วันที่ตัดสินใจ:** 2026-10-21 (commit `1b09671`, merge `43b5eb4`)

## Context

ก่อนหน้านี้ collection รันบนเครื่อง operator เท่านั้น (Windows Task Scheduler ตั้งแต่ 2026-09-30) และ `book-job-data-api` รายงาน `stale` (`scraped_at` ล่าสุด 2026-08-20 ตาม `RUNBOOK.md` §Verified state 2026-10-21) repo เป็น public จึงใช้ GitHub-hosted runner ได้ฟรี

## Decision

รัน `job_postings`, `career_postings`, `job_match_filter` ทุก 6 ชั่วโมง (`17 */6 * * *`) ใน `.github/workflows/scheduled-capture.yml` แล้วให้ `book-job-data` (pin ด้วย `BOOK_JOB_DATA_REF`) ingest `job_postings.csv` และ `matched_jobs.csv` เข้า R2 prefix `portfolio-demo/book-job-data-001` ไม่มี server: "deployment" ของ repo นี้คือข้อมูลที่ publish

## Consequences

- Actions log เป็น public: `scripts/cloud_capture.py` ส่ง output ทั้งหมดไปไฟล์ที่ไม่ upload และพิมพ์ status หนึ่งบรรทัดต่อ job (SPEC-CAP-04)
- บังคับ `seed_tracker` ปิดบน runner; `apply_tracker.csv` ไม่เคยอยู่บน runner (SPEC-CAP-10)
- ความสดขึ้นกับความล่าช้าในการเริ่ม schedule ของ GitHub (KPI-O-01)
- GitHub ปิด schedule เมื่อ repo ไม่มี commit 60 วัน; heartbeat alert คือสัญญาณ (`RUNBOOK.md`)

## Evidence

`.github/workflows/scheduled-capture.yml`, `scripts/cloud_capture.py`, `specs/cloud-capture-pipeline.md`, `RUNBOOK.md` §Hosted job capture, `git log` `1b09671`
