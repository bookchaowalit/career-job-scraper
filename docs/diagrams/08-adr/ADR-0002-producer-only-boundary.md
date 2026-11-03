# ADR-0002 — เป็น producer เท่านั้น: เขียนไฟล์ capture ไม่เขียน database ของระบบอื่น

- **Status:** accepted (retro-documented)
- **วันที่ตัดสินใจ:** 2026-08-11 (`PRODUCT.md` §Status)

## Context

capture ชุดเดียวกันป้อนทั้ง lake product `book-job-data` และ Solo Empire JOB-TRACKER ถ้า scraper ผูกกับ API หรือ storage ของระบบเหล่านั้น ความเป็นเจ้าของ schema (`job.v1`) จะไม่ชัด

## Decision

repo นี้เขียน CSV/JSON ใต้ `data/` เท่านั้น ไม่เรียก Solo Empire API และไม่เขียน Bronze/Parquet เอง `book-job-data` เป็นผู้ ingest ไฟล์; importer ของ JOB-TRACKER (`infra/scripts/opportunities/import_job_applications.py` ใน Solo Empire) อ่าน `confirmed_applications.json`

## Consequences

- ขั้น ingest ใน hosted workflow เรียก CLI `book-job-data` จาก venv แยก ไม่ใช่ library ใน repo นี้
- CSV column contract เป็นของระบบอื่นและยังไม่ถูกเขียนไว้ที่นี่ (`DOCPACK/08-rtm.md` GAP-01)

## Evidence

`BOUNDARY.md`, `PRODUCT.md` §Boundary vs book-job-data, `.github/workflows/scheduled-capture.yml` (Install book-job-data, separate venv), `scripts/cloud_capture.py` `INGEST_FILES`, `CAREER-WORKFLOW.md`
