# ADR-0003 — Live send และ ATS apply ล็อกโดยค่าเริ่มต้น; ส่งด้วยมือพร้อม receipt

- **Status:** accepted (retro-documented)
- **วันที่ตัดสินใจ:** 2026-08-06/07 (`PRODUCT.md` §Status: safety gates + SAFETY.md)

## Context

`scripts/` มี sender หลายตัว (`send_application_emails.py`, `email_application.py`, `auto_send_email.py`, `send_followup_emails.py`, `ats_auto_apply.py`) การส่งถึงนายจ้างโดยไม่ตั้งใจย้อนกลับไม่ได้

## Decision

ทุกเส้นทางส่งจริงต้องมีครบ: CLI flag (`--send` / `--apply`), `BOOK_JOB_LIVE_SEND_ENABLED=1`, `BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND`, `qualification_status=PASS` และ `application_readiness=APPROVED` ส่วน `auto_apply.py` เขียนเฉพาะ `prepared` ไม่เคย `submitted` เส้นทางที่รองรับคือส่งด้วยมือที่ ATS แล้วบันทึกด้วย `application_review.py record-submission` ซึ่งต้องมี packet ที่ owner อนุมัติ ไม่ถูกแก้ และ receipt ไม่ว่าง

## Consequences

- CI ไม่เคยตั้ง unlock env (`ci.yml` permission read-only; `PRODUCT.md` §Dirty-tree triage)
- สถานะ `submitted` มีเฉพาะใน `confirmed_applications.json`

## Evidence

`scripts/safety.py` (`SEND_UNLOCK_VALUE`, `LIVE_SEND_ENABLED_ENV`, `require_live_send`), `scripts/application_review.py` `prepare` / `record_submission`, `SAFETY.md`, `tests/test_paths_and_safety.py`, `tests/test_career_pipeline.py`
