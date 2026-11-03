# Core 22 SDLC diagram pack — career-job-scraper

ชุดภาพ Core 22 ตาม SDLC Diagram Catalog v2 วาดจากโค้ดและ config ใน repo นี้ (ณ `origin/main` `21c3608`, 2026-11-03)
repo นี้คือ Tier A tool (เรียกใน DOCPACK ว่า book-job-scraping / BJS): ไม่มี public URL, เป็น producer ของ job capture ที่ publish เข้า R2 ทุก 6 ชั่วโมง และมีเครื่องมือเตรียมใบสมัครแบบ manual บนเครื่อง operator

ทุกไฟล์มี `Sources:` ใต้ภาพ และ "Open questions" สำหรับสิ่งที่ยืนยันจากโค้ดไม่ได้

| # | Item | Status | File | Sources read |
|---|---|---|---|---|
| 01 | Business process As-Is / To-Be | done | [01-business-process.md](01-business-process.md) | workflows, `scripts/cloud_capture.py`, `scripts/scheduled_run.py`, `config/jobs.yaml`, `scripts/application_review.py`, `PRODUCT.md`, `docs/UPGRADE-PLAN.md`, `BOUNDARY.md` |
| 02 | Use cases | done | [02-use-cases.md](02-use-cases.md) | `DOCPACK/05-srs.md`, `scripts/safety.py`, `mcp_server/server.py`, `chrome-extension/manifest.json`, review scripts |
| 03 | User flows | reused + extended | [03-user-flows.md](03-user-flows.md) → [`DOCPACK/06-ux-flows.md`](../../DOCPACK/06-ux-flows.md) | `chrome-extension/*.js`, `integrations/google-sheet/Code.gs`, importers |
| 04 | Traceability (RTM) | reused + extended | [04-traceability.md](04-traceability.md) → [`DOCPACK/08-rtm.md`](../../DOCPACK/08-rtm.md) | `DOCPACK/05-srs.md`, `specs/cloud-capture-pipeline.md`, `tests/` |
| 05 | C4 Context | done | [05-c4-context.md](05-c4-context.md) | `config/*.yaml`, scrapers, workflow, `_sentry.py`, extension |
| 06 | C4 Container | done | [06-c4-container.md](06-c4-container.md) | workflow, `main.py`, `mcp_server/`, extension, `Code.gs` |
| 07 | C4 Component | done | [07-c4-component.md](07-c4-component.md) | `core/`, `adapters/`, job scripts |
| 08 | ADRs | done (5) | [08-adr/](08-adr/) | git log, workflow, `BOUNDARY.md`, `SAFETY.md`, `core/`, `_sentry.py` |
| 09 | ERD | done (file-based) | [09-erd.md](09-erd.md) | CSV `fieldnames` in scripts, `contracts/*.json`, scheduler/storage adapters |
| 10 | Sequences | done | [10-sequences.md](10-sequences.md) (+ reused `DOCPACK/02-architecture.md` §5.1) | workflow, `cloud_capture.py`, `main.py`, `application_review.py` |
| 11 | State machines | done | [11-state-machines.md](11-state-machines.md) | `job_target_policy.py`, `application_review.py`, `contracts/*.json`, `core/models.py` |
| 12 | API & integrations | done | [12-api-integration.md](12-api-integration.md) | scrapers, workflow, extension, `Code.gs`, `RUNBOOK.md` |
| 13 | Threat model | done | [13-threat-model.md](13-threat-model.md) | `DOCPACK/03-nfr-security.md`, `SAFETY.md`, workflows, extension, `Code.gs` |
| 14 | Backup & DR | done | [14-backup-dr.md](14-backup-dr.md) | `scripts/pipeline_backup.py`, `pipeline_runner.py`, workflow, `RUNBOOK.md` |
| 15 | CI/CD pipeline | done | [15-cicd-pipeline.md](15-cicd-pipeline.md) | `.github/workflows/*.yml`, platform-ci-workflows `ci-python.yml` / `security.yml` @ `87dc5e1c` |
| 16 | Deployment | done | [16-deployment.md](16-deployment.md) | workflow, `ops/windows/scheduled-task.ps1`, `setup_cron.sh`, `RUNBOOK.md` |
| 17 | Test coverage matrix | done | [17-test-coverage-matrix.md](17-test-coverage-matrix.md) | `tests/`, `ci.yml`, `DOCPACK/07-test-uat.md` |
| 18 | Git & release workflow | done | [18-git-release-workflow.md](18-git-release-workflow.md) | `git log --first-parent`, `gh pr list` |
| 19 | Service dependency map | done | [19-service-dependency-map.md](19-service-dependency-map.md) | workflow, `http_policy.py`, `cloud_capture.py`, extension manifest |
| 20 | Observability | reused + extended | [20-observability.md](20-observability.md) → [`docs/measurement/KPI-PLAN.md`](../measurement/KPI-PLAN.md) | `_sentry.py`, workflow, `pipeline_health_monitor.py`, `gh run list` |
| 21 | Incident response | done | [21-incident-response.md](21-incident-response.md) | `RUNBOOK.md`, spec acceptance scenarios, workflow |
| 22 | DORA | done (5/5 computed, with caveats) | [22-dora.md](22-dora.md) | `git log`, `gh run list` (ci.yml, scheduled-capture.yml) |

## ADR list

- [ADR-0001](08-adr/ADR-0001-hosted-capture-on-github-actions-to-r2.md) Hosted capture บน GitHub Actions → R2
- [ADR-0002](08-adr/ADR-0002-producer-only-boundary.md) Producer only boundary
- [ADR-0003](08-adr/ADR-0003-live-send-locked-by-default.md) Live send ล็อกโดยค่าเริ่มต้น
- [ADR-0004](08-adr/ADR-0004-hexagonal-core-yaml-scheduler.md) Hexagonal core + YAML scheduler
- [ADR-0005](08-adr/ADR-0005-error-reporting-sentry-allowlist-scrub.md) Sentry errors only + heartbeat

ADR-01..07 แบบตารางเดิมอยู่ใน [`DOCPACK/02-architecture.md`](../../DOCPACK/02-architecture.md) §7

## Findings worth the owner's attention

- KPI-O-01 (freshness ≤ 8 h) ถูกเกิน 12 ครั้งตั้งแต่ 2026-10-26; start gap สูงสุด 10.0 h (ดู 20)
- ไม่มี commit บน `main` ตั้งแต่ 2026-10-24: GitHub จะปิด schedule หลัง 60 วันไม่มี commit (≈ 2026-12-23) (ดู 14, 21)
- `career-review/` และ `confirmed_applications.json` (หลักฐานการสมัคร) ไม่อยู่ใน backup ใด (ดู 14)
- คอมเมนต์ `ci.yml` อ้าง network guard ใน `tests/conftest.py` ที่ไม่มีแล้ว (ดู 17)
- `DOCPACK/03-nfr-security.md` SEC-07 ยังอ้าง `<all_urls>` ที่ถูกเอาออกตั้งแต่ extension 1.4.0 (ดู 13)

Validate: `node ~/work/core22/tools/validate.mjs docs/diagrams/*.md docs/diagrams/08-adr/*.md`
