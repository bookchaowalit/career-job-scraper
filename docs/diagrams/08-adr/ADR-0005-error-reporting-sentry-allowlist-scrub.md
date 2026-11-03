# ADR-0005 — ส่งเฉพาะ error ไป Sentry ด้วย allowlist scrub; ใช้ heartbeat บอกความมีชีวิต

- **Status:** accepted (retro-documented)
- **วันที่ตัดสินใจ:** 2026-10-23 (commit `9ae9c99`)

## Context

log ของ hosted run เป็น public และ output ของ job มีชื่องาน keyword และ URL ที่มี query แต่ความล้มเหลวยังต้องถึง owner

## Decision

`scripts/_sentry.py` เริ่ม Sentry เฉพาะเมื่อมี `SENTRY_DSN`: ไม่มี tracing, logs, breadcrumbs, `send_default_pii=False`, `include_local_variables=False`; `before_send` เก็บเฉพาะ top-level key และ platform context ใน allowlist และ mask secret กับ URL query ส่วนความมีชีวิตและ step ที่ล้มส่งไป uptime Worker heartbeat `job-capture` (alert ทันทีเมื่อล้ม หรือเงียบเกิน 13 ชม.)

## Consequences

- ไม่มี secret (fork, local, test) = ไม่ import และไม่ส่งอะไร
- ไม่มี performance data ใน Sentry; ระยะเวลา run มาจาก Actions history เท่านั้น (KPI-G-03)

## Evidence

`scripts/_sentry.py`, `tests/test_sentry_scrub.py`, `.github/workflows/scheduled-capture.yml` step Heartbeat, `specs/cloud-capture-pipeline.md` SPEC-CAP-07/08, `docs/measurement/KPI-PLAN.md`
