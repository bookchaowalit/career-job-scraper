# book-job-scraping — Producer Brief & Boundary Contract

*Tier A tool flagship (collection / automation). Nested repo:
`projects/product/engineering/book-dev/github/bookchaowalit/book-apps/tools/book-job-scraping`.*

## Who this is for

The operator (you) who needs **job discovery capture** and **application
prep** pipelines without coupling scraper code to Solo Empire control-plane
APIs or the lake consumer.

## What it is / is not

| Is | Is not |
|---|---|
| Collection + matching + draft/prep tooling | Source of record for analytics |
| Writes capture files under this repo’s `data/` | Writer into another app’s database |
| Optional MCP search over local storage | Hosted job API (`:8109`) |
| Gated send/apply (blocked by default) | Always-on auto-apply production system |
| User-selected property or rendered Facebook Group post export + review queue | Social login, private-group crawl, or automatic outreach |

## Boundary vs `book-job-data` (contract)

```text
book-job-scraping (this repo)
  → produce capture CSVs / JSON under ./data/
       e.g. job_postings.csv, matched_jobs.csv, apply_tracker.csv
  → does NOT call Solo Empire APIs
  → does NOT write Bronze/Parquet itself

book-job-data (sibling path / public Track B repo)
  → ingest capture files (lake-first landing → Bronze job.v1)
  → lineage + DuckDB/API :8109
  → parent may hold a **compatibility mirror** without nested .git

Solo Empire opportunities / JOB-TRACKER
  → canonical “submitted applications” human record (optional bridge)
```

Default handoff input for ingest:

```bash
# From Solo Empire / book-job-data docs:
python -m book_job_data.ingest \
  --input /path/to/book-job-scraping/data/job_postings.csv \
  --data-lake-uri /path/to/lake
```

Env overrides:

| Variable | Purpose |
|---|---|
| `BOOK_JOB_SCRAPING_ROOT` | Override repo root |
| `PIPELINE_DATA_DIR` | Override `./data` |
| `BOOK_JOB_SCRAPING_DATA_DIR` | Used by book-job-data when capture dir moves |

See sibling `../book-job-data/README.md` and
`systems/architecture/job-data-contract-v1.yaml` in Solo Empire for schema
ownership (`job.v1`, privacy class internal).

## Safety model (Verified by unit tests)

Live email/ATS paths require **all** of:

1. Explicit CLI flag (`--send` or `--apply`)  
2. `BOOK_JOB_LIVE_SEND_ENABLED=1`  
3. `BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND`  

`auto_apply.py` writes **`prepared`** (not “submitted”).  
`ats_auto_apply.py --test` is preview-only.

Evidence (2026-08-11):

```bash
python3 -m unittest tests/test_paths_and_safety.py -v
# 17 tests OK
```

Extra fix same day: `ats_auto_apply.py` no longer imports `websockets` at
module load — `--test` / dry-run works without the browser venv so safety
gates stay unit-testable.

Full detail: [`SAFETY.md`](./SAFETY.md).

## Hosted capture (2026-10-23)

- Since 2026-10-21, `.github/workflows/scheduled-capture.yml` runs
  `job_postings`, `career_postings` and `job_match_filter` every 6 hours on
  GitHub Actions and ingests the CSVs into R2 for `book-job-data-api`
  (Track B). The public log shows counts only. Failures reach Telegram via the
  uptime heartbeat `job-capture` and Sentry (`career-job-scraper`, errors
  only, allowlist scrub in `scripts/_sentry.py`).
- Spec: [`specs/cloud-capture-pipeline.md`](specs/cloud-capture-pipeline.md);
  KPIs and baselines: [`docs/measurement/KPI-PLAN.md`](docs/measurement/KPI-PLAN.md).

## Current runtime state (2026-09-30)

- The host moved from Linux to Windows. Collection runs every five minutes
  through Windows Task Scheduler (`ops/windows/scheduled-task.ps1`), which calls
  `scripts/scheduled_run.py` with the repository `.venv` and a portable lock
  (`scripts/file_lock.py`) to prevent overlapping runs. `setup_cron.sh` remains
  the Linux/cron path and uses the same runner semantics.
- The enabled collection surface is nine configured jobs. News, Wongnai,
  Kaidee, SEO, AI tools, crypto, FX, stocks, and DefiLlama yields are
  `migrated` to domain crons. `flight_prices` and `ddproperty_condos` remain
  blocked, while `property_social_leads` is planned behind an official search
  API storage-rights gate. The former `money_opportunities` cross-source lane
  was retired with the shared opportunity synthesis and is no longer scheduled.
- Domain adapters also live in sibling repos with their own crons.
- `config/source_coverage.yaml` tracks 25 jobs across 11 business lanes and
  orders acquisition as API/CLI/RSS before scraping, with a priority queue for
  missing adapters.
- Property/social captures use `property.v1`; rows remain `pending` and
  `not_contacted` until the redacted social-capture validator and a named human
  reviewer approve them.
- Rendered Facebook Group post captures use
  [`contracts/facebook-group-post.v1.json`](contracts/facebook-group-post.v1.json);
  visibility, completeness, and post identity are retained as source evidence,
  while private/unknown rows stay gated and outreach remains locked.
- `chrome-extension/` can capture visible text from the operator’s active
  public tab and export raw property or Facebook Group post CSVs.
  `scripts/scrape_facebook_group_background.py` provides an opt-in Playwright
  runner for the same rendered Group boundary using a dedicated local profile;
  it is not scheduled by the collection cron.
  `scripts/import_property_leads.py` and
  `scripts/import_facebook_group_posts.py` are offline normalizers and source
  gates; they keep explicit owner/co-agent evidence, deduplicate, quarantine
  invalid/non-public rows, and never write the CRM or contact a person.
- Collection health is green when the four core artifacts are fresh:
  `job_postings.csv`, `matched_jobs.csv`, `apply_tracker.csv`, and
  `job_descriptions.csv`.
- The latest verification recorded 1,647 postings, 118 matches, 106
  `discovered` tracker rows, 10 descriptions, and 5 resume variants.
- OpenRouter enrichment, Telegram notifications, and live ATS/email
  submission are optional or gated and were not enabled by this change.

## Architecture notes

- Hexagonal core under `core/` + engine adapters (historical multi-category
  scraping platform narrative in README).  
- Job **application** automation lives mainly under `scripts/` (large surface).  
- Path stabilization: `scripts/repo_paths.py` replaces legacy
  `domains/book-dev/book-scraping` monorepo roots.

## Dirty-tree triage (2026-08-11)

~68 dirty paths. **Dominant cluster: path/safety migration across scripts.**

| Cluster | What | Stance |
|---|---|---|
| A. Path + safety foundation | `scripts/repo_paths.py`, `scripts/safety.py`, `core/config.py`, `SAFETY.md`, `tests/` | Ready for focused review/commit |
| B. Mass script rewrite | ~60 `scripts/*.py` (path migration, gates, no runtime pip) | One logical commit after spot-check of high-risk send scripts |
| C. Config / deps | `config/jobs.yaml`, `requirements.txt`, `README.md`, this PRODUCT | With A or docs commit |
| D. Data | `./data/` runtime (gitignored) | Never commit secrets or live trackers |

**Do not** couple a commit of this tree to parent Solo Empire monorepo commits.
**Do not** enable live send unlock in CI or committed env files.

## Claim hygiene

- **Verified:** Safety unit tests pass; send default-locked; paths resolve under this repo.  
- **Observed:** Scrapers and prep scripts exist; board coverage listed in README.  
- **Planned:** Bridge/retire dual tracker (`data/apply_tracker.csv` vs Solo Empire JOB-TRACKER); optional MCP monetization pricing is **not** production revenue evidence.

## Next improvements

1. Owner-approved nested commit of clusters A → B → C.  
2. Document exact CSV column contract consumed by `book-job-data` ingest (link to job.v1).  
3. Keep live send permanently operator-gated.  
4. Prefer lake ingest for analytics; keep this repo collection-only.

## Status

- **2026-08-06/07:** Path migration + safety gates + SAFETY.md.  
- **2026-08-11:** Producer contract PRODUCT.md; tests re-verified 17/17; no bulk commit.
- **2026-08-24/25:** Collection cron and health monitor verified end-to-end; core
  artifacts green; absent adapter jobs explicitly disabled.
- **2026-08-25:** Nested commit of coverage registry, enabled adapters, and
  tests. NotebookSpec RSS enabled. DDproperty parser ready but httpx blocked.
