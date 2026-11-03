# 21 — Incident response

solo operator ไม่มี on-call หลายคน (`RUNBOOK.md` §Owner) ช่องทาง alert จริงที่พบ: Telegram จาก uptime Worker heartbeat `job-capture` และอีเมลจาก Sentry
ไม่พบ template postmortem หรือ incident log ใน repo นี้

```mermaid
flowchart TD
  A1["Heartbeat ok false: capture or ingest failed"] --> T
  A2["Heartbeat silent over 13 h"] --> T
  A3["Sentry email: exception or job failed, tag job"] --> T
  A4["Local: health monitor shows stale artifact"] --> T
  T{"Triage: which signal?"}
  T -->|"silence"| S1["gh run list --workflow scheduled-capture.yml"]
  S1 --> S2{"Schedule disabled after 60 days idle?"}
  S2 -->|"yes"| S3["gh workflow enable scheduled-capture.yml"]
  S2 -->|"no"| S4["Check GitHub status, dispatch: gh workflow run scheduled-capture.yml"]
  T -->|"capture failed"| C1["Read the job failed line in the public log and the Sentry event"]
  C1 --> C2{"Board change or block?"}
  C2 -->|"yes"| C3["Fix parser or drop board in config/jobs.yaml with source_coverage.yaml"]
  C2 -->|"code bug"| C4["Fix, run offline pytest, push to main"]
  T -->|"ingest failed"| I1{"No capture files?"}
  I1 -->|"yes"| C1
  I1 -->|"no"| I2["Check R2 secrets, BOOK_JOB_DATA_REF, book-job-data CLI"]
  T -->|"local stale"| L1["main.py run job_postings, read data/logs/cron.log"]
  C3 --> V["Verify: dispatch a run, three ok lines, heartbeat ok, API /v1/metadata data_status ok"]
  C4 --> V
  I2 --> V
  S3 --> V
  S4 --> V
  L1 --> V2["Verify: pipeline_runner.py --health green"]
  V --> R{"Need rollback?"}
  R -->|"yes"| RB["gh workflow disable scheduled-capture.yml, remove heartbeat target"]
  R -->|"no"| PM["Postmortem: not defined in repo, record in RUNBOOK Verified state"]
  V2 --> PM
```

Sources: `.github/workflows/scheduled-capture.yml`, `scripts/_sentry.py`, `scripts/cloud_capture.py`, `scripts/pipeline_health_monitor.py`, `scripts/pipeline_runner.py`, `RUNBOOK.md` §Hosted job capture, §Health check, §Rollback, §Verified state, `specs/cloud-capture-pipeline.md` acceptance scenarios, `docs/measurement/KPI-PLAN.md`

## Open questions

- ต้องการ template postmortem / incident log ที่ไหน (ไม่มีใน repo; RUNBOOK ใช้หัวข้อ "Verified state" แทน)
- Sentry alert rule เป็น default (email) ตาม KPI-PLAN: ต้องการส่งเข้า Telegram ด้วยหรือไม่
