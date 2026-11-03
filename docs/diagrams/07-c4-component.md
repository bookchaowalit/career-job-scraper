# 07 — C4 Component

Component ของ Python core (hexagonal: `core/` + `adapters/`) และ job scripts ที่ scheduler โหลดแบบ dynamic
(`main.load_category_scraper` อ่าน `scraper_module` / `scraper_class` จาก `config/jobs.yaml`)
ตาราง component เดิมอยู่ใน [`DOCPACK/02-architecture.md`](../../DOCPACK/02-architecture.md) §2

```mermaid
C4Component
  title Python core and job pipeline - Components
  Container_Boundary(py, "Python process: main.py or cloud_capture.py") {
    Component(root, "Composition root", "main.py build_system", "Wires scheduler, engine, exporter, storage, use case")
    Component(sched, "SchedulerAdapter", "adapters/inbound/scheduler_adapter.py", "Loads config/jobs.yaml, state in data/schedule_state.json")
    Component(uc, "ScrapeUseCase / SearchUseCase", "core/use_cases.py", "scrape, clean, dedup, export, save; search with filters")
    Component(clean, "DataCleaner + Deduplicator", "core/pipeline/", "Thai text normalisation, content hash in data/hash_db.json")
    Component(eng, "EngineAdapter", "adapters/outbound/engine_adapter.py", "httpx, playwright, selenium, rss, firecrawl, jina engines")
    Component(exp, "ExporterAdapter", "adapters/outbound/exporter_adapter.py", "json, csv, sqlite, parquet")
    Component(store, "StorageAdapter", "adapters/outbound/storage_adapter.py", "data/<collection>/items.json, atomic write")
    Component(jp, "JobPostingScraper", "scripts/scrape_job_postings.py", "Remote boards to job_postings.csv + history")
    Component(cd, "CareerDiscovery", "scripts/career_discovery.py", "Greenhouse boards to career_postings.csv")
    Component(mf, "JobMatchFilter", "scripts/filter_job_matches.py", "Score + policy to matched_jobs.csv; optional seed")
    Component(pol, "Target policy", "scripts/job_target_policy.py", "PASS / VERIFY / REJECT from config/job_targeting.yaml")
    Component(http, "HTTP policy", "scripts/http_policy.py", "Per-host spacing, retry on 429/5xx, circuit breaker")
    Component(seed, "auto_seed", "scripts/auto_seed_tracker.py", "PASS rows to apply_tracker.csv as discovered")
    Component(sen, "Sentry wrapper", "scripts/_sentry.py", "init, capture, allowlist scrub")
  }

  Rel(root, sched, "Creates")
  Rel(root, uc, "Creates with ports")
  Rel(uc, eng, "ScraperPort")
  Rel(uc, clean, "Clean and dedup")
  Rel(uc, exp, "ExporterPort")
  Rel(uc, store, "StoragePort")
  Rel(root, jp, "Dynamic load for job_postings")
  Rel(root, cd, "Dynamic load for career_postings")
  Rel(root, mf, "Dynamic load for job_match_filter")
  Rel(jp, http, "polite get")
  Rel(cd, pol, "qualify_job, drop REJECT")
  Rel(mf, pol, "qualify_job")
  Rel(mf, seed, "if seed_tracker")
```

Sources: `main.py`, `core/use_cases.py`, `core/ports.py`, `core/pipeline/cleaner.py`, `core/pipeline/deduplicator.py`, `adapters/inbound/scheduler_adapter.py`, `adapters/outbound/engine_adapter.py`, `adapters/outbound/exporter_adapter.py`, `adapters/outbound/storage_adapter.py`, `scripts/scrape_job_postings.py`, `scripts/career_discovery.py`, `scripts/filter_job_matches.py`, `scripts/job_target_policy.py`, `scripts/http_policy.py`, `scripts/auto_seed_tracker.py`, `scripts/_sentry.py`, `config/jobs.yaml`

หมายเหตุ: job ที่มี `scraper_module` (ทุก job ที่ enabled) ไม่ผ่าน `ScrapeUseCase`; `execute_job` เรียก `scraper.run()` ตรง ส่วน `ScrapeUseCase` ใช้เมื่อ job ไม่มี module (generic engine path)

## Open questions

- `scripts/job_role_relevance.py`, `scripts/job_dedup.py` ถูกเรียกจาก job ไหนใน path ที่ schedule จริง (ไม่ได้ trace ลึกในรอบนี้)
