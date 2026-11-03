# ADR-0004 — Hexagonal core กับ scheduler ในตัวที่อ่าน YAML

- **Status:** accepted (retro-documented)
- **วันที่ตัดสินใจ:** ไม่ได้บันทึก (เกิดก่อน history ใน repo นี้; อธิบายใน `README.md` §Architecture (Hexagonal))

## Context

platform เริ่มจาก scraper หลายหมวด (jobs, products, property, news) ที่มี fetch engine หลายแบบ

## Decision

domain model และ port อยู่ใน `core/` (`ScrapedItem`, `ScrapeJob`, `ScraperPort`, `ExporterPort`, `StoragePort`, `SchedulerPort`); engine, storage, export เป็น adapter job ประกาศใน `config/jobs.yaml` และโหลดโดย `SchedulerAdapter`; `main.py` โหลด `scraper_module`/`scraper_class` ของแต่ละ job แบบ dynamic ไม่ใช้ APScheduler: `ScrapeJob.is_due()` map cron string บางแบบเป็นช่วงเวลา และให้ตัวจับเวลาภายนอก (Task Scheduler, cron, Actions) เป็นผู้เรียก tick

## Consequences

- `is_due()` เข้าใจเฉพาะ cron string ใน map; string อื่นตกเป็น daily (เช่น `15 8,11,20 * * *` ของ `scraper_dashboard`)
- เพิ่ม job = เพิ่ม YAML + entry ใน `config/source_coverage.yaml` (`RUNBOOK.md` §Review source coverage)

## Evidence

`core/models.py`, `core/ports.py`, `core/use_cases.py`, `adapters/inbound/scheduler_adapter.py`, `main.py`, `config/jobs.yaml`, `DOCPACK/02-architecture.md` ADR-01
