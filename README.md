# Book Job Scraping — Multi-Engine Capture + Job Pipeline

International remote career changes and relocation now have separate review
lanes. See [Career workflow](CAREER-WORKFLOW.md) for public company discovery,
review packets, exact-document preparation and receipt-backed manual
submission tracking. Live automated ATS submission remains unverified.

Hexagonal-architecture scraping platform with 5 engines, scheduled jobs,
MCP search over local storage, and a **job application prep** pipeline.

**Canonical nested path:**
`projects/product/engineering/book-dev/github/bookchaowalit/book-apps/tools/book-job-scraping/`
**Architecture:** Hexagonal (Ports & Adapters)
**Engines:** httpx+BS4, Playwright, Selenium, Scrapy, RSS
**Categories:** Jobs, E-commerce, Restaurants, Directories, News, Property

**Producer contract / safety:** see [`PRODUCT.md`](./PRODUCT.md) and
[`SAFETY.md`](./SAFETY.md). This repo is **collection + prep only** —
durable lake analytics live in sibling **`book-job-data`** (ingest capture
CSVs → Bronze `job.v1` → API `:8109`). Do not write Solo Empire SQLite or
another app DB from here.

---

## Architecture (Hexagonal)

```
book-scraping/
│
├── core/                       # Domain layer — zero external dependencies
│   ├── models.py               # ScrapedItem, JobListing, ProductListing, ScrapeJob...
│   ├── ports.py                # ScraperPort, ExporterPort, StoragePort, SchedulerPort
│   ├── use_cases.py            # ScrapeUseCase (pipeline), SearchUseCase (MCP)
│   └── pipeline/               # Data cleaning + deduplication
│       ├── cleaner.py          # Thai-specific normalization, contact extraction
│       └── deduplicator.py     # Content-hash dedup with persistent DB
│
├── adapters/                   # Implementation layer
│   ├── inbound/                # Drivers — things that call INTO the core
│   │   └── scheduler_adapter.py    # YAML-driven job scheduler + CLI
│   └── outbound/               # Driven — things the core calls OUT to
│       ├── engine_adapter.py   # Routes to correct engine by job.engine
│       ├── exporter_adapter.py # JSON, CSV, SQLite, Parquet export
│       ├── storage_adapter.py  # File-based storage by category
│       ├── engines/            # Actual scraping engines
│       │   ├── base.py         # BaseScraper (rate limit, cache, retry)
│       │   ├── httpx_bs4.py    # Static HTML — fast, lightweight
│       │   ├── playwright_engine.py  # JS-rendered SPAs
│       │   ├── selenium_engine.py    # Complex interactions (login, scroll)
│       │   ├── scrapy_engine.py      # Large-scale crawls (10K+ pages)
│       │   └── rss_engine.py         # RSS/Atom feeds
│       └── utils/              # Shared engine utilities
│           ├── user_agents.py      # UA pool rotation
│           ├── proxy_rotator.py    # Proxy pool + health check
│           ├── anti_detect.py      # Fingerprint randomization
│           ├── validators.py       # Data schema validation
│           └── exporters.py        # Legacy export helpers
│
├── jobs/                       # Website-specific scrapers (inherit from engines)
│   └── jobsdb_scraper.py       # Jobsdb Thailand
│
├── mcp_server/                 # MCP data-as-a-service (inbound adapter)
│   └── server.py               # Uses SearchUseCase → StorageAdapter
│
├── config/
│   └── jobs.yaml               # 23 configured jobs; 9 enabled in this checkout
│
├── templates/                  # Copy-paste templates for new scrapers
│   ├── new_httpx_scraper.py
│   └── new_playwright_scraper.py
│
├── main.py                     # CLI entry point (composition root)
├── requirements.txt
└── data/                       # Scraped data (gitignored)
    ├── jobs/items.json
    ├── products/items.json
    ├── businesses/items.json
    ├── news/items.json
    └── ...
```

### Data Flow

```
CLI/Scheduler (inbound)
    → ScrapeUseCase (core)
        → EngineAdapter.scrape()     [outbound: engines/]
        → DataCleaner.clean()        [core: pipeline/]
        → Deduplicator.deduplicate() [core: pipeline/]
        → ExporterAdapter.export()   [outbound: exporters]
        → StorageAdapter.save()      [outbound: storage]
```

---

## Scheduled Jobs

Jobs are defined in `config/jobs.yaml`. The installed local scheduler (Windows
Task Scheduler via `ops/windows/scheduled-task.ps1`, or cron via
`setup_cron.sh` on Linux) invokes `main.py run` every five minutes, so only jobs due at that moment are run.
The scheduler state is written to `data/schedule_state.json`.

| Job | Category | Engine | Schedule | Status |
|-----|----------|--------|----------|--------|
| `github_trending` | discovery | httpx | Daily 10:00 AM | enabled |
| `hackernews` | discovery | httpx | Daily 9:00 AM | enabled |
| `devto_articles` | discovery | httpx | Daily 10:00 AM | enabled |
| `producthunt_top` | discovery | httpx | Daily 11:00 AM | enabled |
| `ai_tools` | ai | Futurepedia HTML | Daily 11:00 AM | migrated to book-ai-tools-data |
| `property_listings` | property | firecrawl + bounded public fallback | Daily 9:00 AM | enabled (degraded: direct DDproperty 403; fallback only) |
| `property_social_leads` | property | Brave Search API public index (no social login) | Every 6 hours | conditional / disabled |
| `tgcondo_condo_rent` | property | TG Condo public RSS | Every 6 hours | planned / disabled pending terms review |
| `ennxo_condo_sale` | property | ENNXO public HTML | Daily 9:00 AM | planned / disabled pending terms review |
| `propertyhub_condo_rent` | property | PropertyHub public HTML | Daily 10:00 AM | planned / disabled pending terms review |
| `livinginsider_condo_rent` | property | LivingInsider public HTML | Daily 11:00 AM | planned / disabled pending terms review |
| `zmyhome_condo_rent` | property | ZmyHome public HTML | Daily 12:00 PM | planned / disabled pending terms review |
| `ddproperty_condos` | property | httpx + Thai `__NEXT_DATA__` | Daily 8:00 AM | blocked: httpx Cloudflare 403 |
| `crypto_prices` | finance | CoinGecko API | Every 4 hours | migrated to book-crypto-data |
| `exchange_rates` | finance | Frankfurter API | Every 6 hours | migrated to book-fx-data |
| `stock_prices` | finance | Yahoo Finance chart API | Daily 8:00 AM | migrated to book-stock-data |
| `defi_yields` | finance | DefiLlama pools API | Daily 7:00 AM | migrated to book-defi-data |
| news / Kaidee / Wongnai jobs | — | — | — | removed 2026-09-30; owned by book-news-, book-ecommerce-, book-restaurant-scraping |
| `flight_prices` | travel | firecrawl+httpx | Weekly Mon 7:00 AM | disabled (`scripts.scrape_flight_prices` not in this checkout) |
| `seo_rankings` | marketing | httpx public pages | Daily 8:00 AM | migrated to book-seo-data |
| `job_postings` | jobs | firecrawl+httpx | Every 6 hours | enabled |
| `career_postings` | jobs | httpx (public company ATS pages) | Every 6 hours | enabled |
| `job_match_filter` | jobs | local | Every 6 hours, after capture | enabled |
| `scraper_dashboard` | operations | local | 8:15, 11:15, 20:15 | enabled |

The coverage registry still holds `flight_prices` and `ddproperty_condos`
behind their source gates, and holds `property_social_leads` as conditional
until a bounded public-search smoke and terms review pass. The
former cross-source `money_opportunities` lane was retired with the shared
opportunity synthesis; it is no longer scheduled or a collection target.
`ddproperty_condos` has a Thai `__NEXT_DATA__` parser and fixture but live
collection hits a Cloudflare JS challenge. `seo_rankings` is enabled as a
public-page provenance check (no SERP ranks on the free path). News RSS,
Kaidee, and Wongnai jobs were migrated to `book-news-scraping`,
`book-ecommerce-scraping`, and `book-restaurant-scraping`, and their code was
removed from this repository on 2026-09-30.
`ai_tools` is enabled
after a six-page Futurepedia HTML smoke returned 62 unique tools with category
and canonical URL attribution.
`crypto_prices` is enabled after the CoinGecko API smoke returned 20 validated
rows. `exchange_rates` is enabled after a Frankfurter smoke returned 10
validated rates, and `stock_prices` is enabled after Yahoo Finance returned 9
validated ticker rows. Re-enable other sources only after a
focused smoke test produces a trustworthy contract-compliant result.
`defi_yields` is migrated to `book-defi-data` after a Firefox-UA live smoke
returned 20 validated Ethereum pools with a provider timestamp within the
24-hour freshness bound. The domain cron uses the same five-chain production
bounds as the previous local job.

The four planned portal adapters (`ennxo`, `propertyhub`, `livinginsider`, and
`zmyhome`) write separate `property_<source>_listings.csv` supply snapshots.
They use source-specific selectors, canonical detail URLs, positive-price
filters, and public contact fields that remain pending human review. They do
not write the Pantip-only `property-demand.v1` handoff. Keep these jobs
disabled until source terms, robots observations, retention, and the public
contact storage basis are documented.

### Multi-business source coverage

`config/source_coverage.yaml` is the coverage registry for the shared
acquisition platform. It maps every scheduler job to a business lane, source,
acquisition channel, output contract, implementation status, and restoration
priority. The preferred acquisition order is API, CLI, RSS, then scraping;
`hybrid` entries may combine an API with bounded HTML fallback.

```bash
python scripts/source_coverage.py --check
python scripts/source_coverage.py
python scripts/source_coverage.py --json
```

The validator fails if coverage drifts from `config/jobs.yaml`, an enabled
adapter module is missing, or a source has no contract/next action. This keeps
business coverage broad without making every downstream application scrape
independently.

The DDproperty adapter writes its collection-only snapshot to
`data/exported/ddproperty_condos.csv` and reuses the shared property parser;
it does not own matching, alerts, or downstream business decisions.

Property rows now include explicit public contact fields (`contact_role`,
`co_agent_status`, phone/email/LINE, and platform URLs), the source URL and a
short evidence snippet.  `lead_review_status=co_agent_candidate` is only a
review queue signal; it never sends outreach or proves that a person is the
owner.  Every row also starts with `review_decision=pending` and
`outreach_status=not_contacted`; a reviewer must record the decision before any
outreach status can advance.  The social lead adapter searches publicly
indexed Facebook, Instagram, TikTok, and LINE URLs and stores result metadata in
`data/exported/property_social_leads.csv`.  It queries the official Brave
Search API only; it does not scrape the search UI, authenticate to, crawl, or
bypass private social content.  Persisting API results requires a Brave plan
that explicitly grants storage rights, plus source-terms/PDPA review and
human contact-quality review.  Keep the job disabled until those gates pass.

### Public property-seeker demand (direct HTTP only)

The demand lane is separate from `property.v1` listing/owner captures. It uses
`scripts/scrape_property_demand.py` to fetch only public Pantip search and topic
HTML with `httpx`; it does not use browser automation, author profiles, login
sessions, or private groups. `robots.txt`, an HTTPS Pantip host allowlist,
redirect and response-size bounds, request pacing, and a topic limit are
enforced by the collector. The command is a dry run by default and is not
registered with the scheduler.

```bash
python scripts/scrape_property_demand.py \
  --query "หาคอนโดเช่า" --limit 10 --dry-run --json
python scripts/scrape_property_demand.py \
  --url https://pantip.com/topic/44155476 --dry-run --json
```

For a larger handoff, repeat several public search queries and use the bounded
100-topic ceiling. Parsed records are ordered by `posted_at` newest-first;
records without a trustworthy timestamp remain at the end for review:

```bash
python scripts/scrape_property_demand.py \
  --query "หาคอนโดเช่า" \
  --query "หาเช่าคอนโด" \
  --query "หาห้องเช่า" \
  --query "หาบ้านเช่า" \
  --query "หาซื้อคอนโด" \
  --query "อยากซื้อบ้าน" \
  --limit 100 --max-age-days 30 --dry-run --json
```

First-person seeker text is written to `property-demand.v1` fields only after
the parser separates it from listing, owner, agent, and co-agent language.
Missing or stale post timestamps become `needs_more_evidence`; otherwise the
default remains `permission_needed`. A public topic URL is a review path, not
permission to call, and the collector never enriches a phone number from a
profile or hidden page. `call_ready` is reserved for a later human decision and
is never emitted automatically.

Persisting a review packet requires an explicit retention deadline and a
source-terms reference. The default CSV handoff is UTF-8 with BOM so Thai text
opens correctly in spreadsheet tools; it contains only `call_ready`,
`permission_needed`, and `needs_more_evidence` rows. `not_demand` rows are
excluded. JSONL remains available with `--format jsonl` for replay/debugging:

```bash
python scripts/scrape_property_demand.py --persist \
  --retention-until 2026-12-31T00:00:00Z \
  --terms-basis-ref "human-reviewed-public-source-terms" \
  --query "หาคอนโดเช่า"
```

The default output is `data/exported/property_demand.csv`; use `--output` to
choose another handoff path. This lane never writes Solo Empire CRM/SQLite and
never sends outreach. The CSV is a review handoff, not permission to contact.

The contract is [`contracts/property-demand.v1.json`](contracts/property-demand.v1.json).

### Major-source audit

Run the bounded HTTP/robots audit alongside the demand handoff:

```bash
python scripts/audit_property_demand_sources.py \
  --output data/exported/property_demand_source_audit.csv --json
```

The audit records source metadata only. It keeps major portals such as Kaidee,
ENNXO, PropertyHub, RentHub, LivingInsider, Zmyhome, Meezub, DotProperty,
Baania, and Hipflat visible, but marks their sale/rent pages as
`exclude_demand` because they publish supply listings rather than first-person
buyer/renter requests. DDproperty remains blocked. Reddit and ASEANN remain
blocked until an approved API/export path is available. Facebook public groups
are `manual_export_only` and must use the existing user-selected public export
flow; this command never crawls them.

The row shape is versioned in
[`contracts/property-capture.v1.json`](contracts/property-capture.v1.json).
Validate a persisted social capture without printing contact values before
lake ingest:

```bash
python scripts/check_property_social_capture.py \
  data/exported/property_social_leads.csv --json --require-governance
```

Run the complete social extraction and review flow locally with the synthetic
fixture; this mode is offline and does not need an API key:

```bash
mkdir -p /tmp/property-social-fixture
python scripts/scrape_property_social.py \
  --fixture tests/fixtures/property_social_results.json \
  --limit 20 --output-dir /tmp/property-social-fixture
python scripts/check_property_social_capture.py \
  /tmp/property-social-fixture/property_social_leads.csv --json
```

Fixture rows are synthetic examples for parser and workflow checks. They do
not prove live source access or permit enabling the scheduled collector.

### Owner / co-agent capture from a browser export

The repository now has a manual, offline bridge for the sources that publish
explicit owner or cooperation wording.  It accepts a CSV/JSON export from the
included Chrome extension or another browser exporter and keeps only rows
whose visible text contains an explicit owner/co-agent signal.  The current
allowlist includes `zmyhome.com`, `meezub.com`, `ennxo.com`,
`livinginsider.com`, the configured property portals, and public URLs on
Facebook, Instagram, TikTok, and LINE.  A URL is never fetched by the
importer; unsupported, non-HTTPS, or look-alike hosts are quarantined.
DDproperty remains blocked by its source terms and is not accepted by this
manual importer.

To use the included extension, open the `chrome-extension/` directory in
`chrome://extensions` with **Developer mode → Load unpacked**.  On a public
listing or public search page that you opened yourself, click **Capture public
property lead**, check the visible evidence, save the row, then click
**Export CSV for importer**.  The extension stores rows locally in Chrome and
does not call a backend.  It is a capture aid, not a social crawler: do not
use it on private groups, do not bypass a login or access control, and do not
export browser history or cookies.

Import the downloaded file with the following command:

```bash
python scripts/import_property_leads.py \
  --input ~/Downloads/property_owner_coagent_export.csv \
  --output-dir data/exported
```

The command writes `property_owner_coagent_leads.csv`, an append-only history,
a redacted quarantine report, a checksum manifest, and a local copy of the
input bytes.  Rows start with `review_decision=pending` and
`outreach_status=not_contacted`; no message is sent.  Use
`--include-unqualified` only when you intentionally want a wider manual
review queue.  For a completely offline smoke test:

```bash
python scripts/import_property_leads.py \
  --input tests/fixtures/property_owner_coagent_export.csv \
  --output-dir /tmp/property-owner-coagent-sample
python scripts/check_property_capture.py \
  /tmp/property-owner-coagent-sample/property_owner_coagent_leads.csv --json
```

The fixture is synthetic.  Live owner/co-agent evidence must come from the
public page or export the reviewer actually inspected, and source terms,
privacy purpose, retention, and contact approval still need a human decision
before any CRM or outreach handoff.

### Facebook Group post capture (free, user-selected)

The extension also has **Capture Facebook Group posts**.  Open the Group in a
Chrome tab you are allowed to use, load the extension, click the button, and
select only the rendered posts that have a permalink.  It reads the current
DOM only; it does not call Facebook APIs, open another post, read cookies, or
send a request.  Confirm the Group visibility in the popup before saving.  The
button captures the posts already rendered on screen; scroll yourself and use
**Capture next rendered page** for another page of results, or press
**🤖 Auto-scroll capture** to let the extension scroll this tab for you: one
screen every 4 s, expanding "See more", up to 40 posts or 5 minutes, stopping
early when nothing new appears or it reaches a post you already saved.  **⏹
Stop** ends it at any time.  Posts collect in the capture draft; review them,
pick the visibility, and Save as usual.  Leave the tab in front while it runs
(Chrome slows timers in background tabs).  Scrolling automatically may break
Facebook's terms and risks the account you are logged in with.

Export with **Export Facebook Group CSV**, then run the offline importer:

```bash
python scripts/import_facebook_group_posts.py \
  --input ~/Downloads/facebook_group_posts_export.csv \
  --output-dir data/exported
python scripts/check_facebook_group_capture.py \
  data/exported/facebook_group_posts.csv --json
```

If you only want the posts in the current draft, use **Export current capture
CSV** before saving.  It downloads `facebook_group_current_capture.csv` and
does not clear or add to the saved-posts store.  **Export Facebook Group CSV**
continues to export the posts already saved in the extension.

The popup keeps the capture list while it is open and also stores a bounded
local draft (up to 500 posts, expiring after 24 hours), because Chrome may close
a popup when you return to the tab to scroll.  Reopen the popup and click
**Capture next rendered page**; the next batch is merged by canonical
`post_url` and the better text/metadata copy wins.  Click **Clear capture draft**
when starting over.  This avoids having to save each viewport separately while
still keeping the capture bounded to the posts visible in the tab.

Run the synthetic smoke before using a real export.  It makes no network
request and contains only fake values:

```bash
python scripts/import_facebook_group_posts.py \
  --input tests/fixtures/facebook_group_posts_export.csv \
  --output-dir /tmp/facebook-group-fixture
python scripts/check_facebook_group_capture.py \
  /tmp/facebook-group-fixture/facebook_group_posts.csv --json
```

The validator reports accepted row count, visibility counts, incomplete text,
duplicate URLs/IDs, candidate count, and pending-review count.  Use
`--require-complete` when a downstream step must reject any post whose visible
text still contains a “See more” boundary.  Warnings never approve outreach;
rows still start at `review_decision=pending` and `outreach_status=not_contacted`.

Review selected rows after checking the original Group tab.  The command only
records a decision and keeps outreach locked:

```bash
python scripts/review_facebook_group_posts.py \
  --input data/exported/facebook_group_posts.csv \
  --rows 1,3 --decision approved --reviewer-id owner-1 \
  --output data/exported/facebook_group_posts_reviewed.csv
python scripts/check_facebook_group_capture.py \
  data/exported/facebook_group_posts_reviewed.csv --json
```

The row contract is versioned in
[`contracts/facebook-group-post.v1.json`](contracts/facebook-group-post.v1.json).
The importer canonicalises Facebook Group/post URLs, removes tracking query
parameters, deduplicates posts, extracts explicit owner/co-agent signals from
the supplied post text, and starts every row at `review_decision=pending` and
`outreach_status=not_contacted`.  Public rows remain available for review even
when they have no owner signal; use `--candidates-only` when you want a strict
owner/co-agent queue.  Private or `unknown` rows are quarantined by default.
To process a row from a group you are authorised to use, pass both an explicit
gate and governance references:

```bash
python scripts/import_facebook_group_posts.py \
  --input ~/Downloads/facebook_group_posts_export.csv \
  --allow-private --allow-unknown \
  --retention-until 2026-12-31T00:00:00Z \
  --terms-basis-ref group-owner-approved-2026-09-14 \
  --output-dir data/exported
```

This does not bypass a login or make private content public.  The output is a
review queue, not a CRM write or outreach trigger.  A synthetic no-network
smoke test is available at
`tests/fixtures/facebook_group_posts_export.csv`; it does not prove live
Facebook access.

### Site access

Since 1.4.0 the extension has no `<all_urls>` access.  Its page script runs
only in the tab where you open the popup (`activeTab` + `scripting`), plus
automatically on the listed job boards for the floating save button.  Capturing
a property page or a Facebook Group therefore starts by clicking the extension
icon on that tab, as before.

### Upload exports to your own cloud storage (optional)

The extension can also upload every CSV it exports (property rows, the current
Facebook Group capture, and saved Group posts) to the operator's own Google
Drive, Dropbox, or OneDrive.  It is off by default.  The local download still
happens; the upload is in addition to it, and each provider reports its own
result in the popup and on the options page.

Setup, once per provider:

1. Click ☁️ in the popup to open the options page and copy the **Redirect
   URI**.  It is the same on every machine,
   `https://gbipaflofmmmglinopjefeffngikmggb.chromiumapp.org/`, because the
   manifest pins the extension ID with a public `key`.
2. Register an OAuth app with that redirect URI and paste its client ID.  The
   options page lists the clicks for each provider.  No client secret is used.
   - Google Drive: *Web application* client, scope `drive.file` (the extension
     only sees files it created).
   - Dropbox: *App folder* app with `files.content.write`; PKCE, no secret.
   - OneDrive: app registration with *Access tokens (implicit flow)* and
     `Files.ReadWrite.AppFolder` (files land in `Apps/<app name>/`).
3. Tick **เปิดใช้**, click **เชื่อมต่อ** to sign in, tick **อัปโหลดทุกครั้งที่
   export**, and save.

**Upgrading from 1.1.0:** version 1.2.0 pins the extension ID, so Chrome
treats it as a new extension and its storage starts empty.  Before loading
1.2.0, open the old popup and export anything you still need (property CSV,
Facebook Group CSV), then remove the old extension.

Files are named `<export name>_<UTC timestamp>.csv` inside the chosen folder
(default `Quick Saver`), so repeated exports never overwrite each other.
Access tokens live only in `chrome.storage.session` and are dropped when Chrome
closes; the next export asks the provider again (usually without a prompt).
The private key behind the manifest `key` is kept outside the repository at
`~/.config/quick-saver/extension-key.pem`; it is only needed to pack a `.crx`.

### Send Facebook Group posts to a Google Sheet (optional)

Posts you **Save** (and the current capture when you **Export current capture
CSV**) can also be appended to a Google Sheet tab `raw_posts`.  Off by default.
Only rows from a group you labelled **Public** are sent; private and unknown
rows stay in the browser, the same rule the importer applies.

1. Open the target Sheet → Extensions → Apps Script, paste
   [`integrations/google-sheet/Code.gs`](integrations/google-sheet/Code.gs).
2. Project Settings → Script properties → add `SECRET` with a long random value
   and `SPREADSHEET_ID` (the id in the Sheet URL, `/spreadsheets/d/<id>/edit`).
3. Deploy → New deployment → Web app, *Execute as: Me*, *Who has access:
   Anyone*.  Copy the `/exec` URL.
4. In the extension's ☁️ options page, paste the URL and the same secret, tick
   **เปิดใช้**, click **ทดสอบการเชื่อมต่อ** (sends an empty batch), then save.

**Updating to 1.4.0:** permalinks are now canonical
(`https://facebook.com/groups/<g>/posts/<id>`, no `__cft__`/`__tn__` query),
so dedup works across page loads.  Paste the new `Code.gs`, then *Deploy →
Manage deployments → Edit → New version* (the `/exec` URL stays the same), and
run `cleanUpDuplicatePermalinks` once from the editor to rewrite old rows and
delete the duplicates they produced.

Columns: `collected_at` (ISO, Asia/Bangkok), `group_name`, `group_url`,
`permalink`, `poster`, `posted`, `text`, `text_complete`, `processed`.  The
script deduplicates by permalink and stores cells that start with `= + - @` as
text.  A failed send is retried once; undelivered rows (up to 2000 rows or
about 4 MB) stay queued in the extension and go with the next save.  Re-saving a
post as private or unknown withdraws it from that queue.  The web app is reachable by anyone
who has the URL, so the secret is what protects it: keep both private and
rotate the secret (Script properties + options page) if either leaks.

### Background capture without the extension (opt-in)

Use `scripts/scrape_facebook_group_background.py` when you want a local
Playwright process instead of the popup.  It opens only the Group URLs in a
local text/JSON file, reads rendered `[role="article"]` nodes, performs a
bounded number of manual-equivalent scroll rounds, and writes the same raw CSV
shape with `capture_method=playwright_visible_tab`.  It is not scheduled by
`setup_cron.sh`.

Create a dedicated browser profile outside the repository.  The first command
opens a headed browser so you can log in or complete a checkpoint yourself;
the runner never exports or prints cookies:

If Debian/Ubuntu reports that `ensurepip` is unavailable, install the matching
venv package once, then recreate the project environment:

```bash
sudo apt update
sudo apt install python3.14-venv
python3 -m venv --clear .venv
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install-deps chromium
```

The shorter install above is sufficient for this runner; install the full
`requirements.txt` only when using the other scrapers in this repository.

```bash
.venv/bin/playwright install chromium
.venv/bin/python scripts/scrape_facebook_group_background.py \
  --profile-dir ~/.local/share/solo-empire/facebook-playwright \
  --login-only --headed
```

Then create a local URL list and run a bounded headless capture:

```text
# /tmp/facebook-groups.txt
https://facebook.com/groups/your-authorised-group
```

```bash
.venv/bin/python scripts/scrape_facebook_group_background.py \
  --groups-file /tmp/facebook-groups.txt \
  --profile-dir ~/.local/share/solo-empire/facebook-playwright \
  --output /tmp/facebook-group-background.csv \
  --rounds 3 --pause-ms 1500 --visibility public
```

Before using a real Group, run the browser path against the synthetic fixture;
the `--fixture` option serves the document locally, aborts other intercepted
page requests, and never navigates to Facebook:

```bash
.venv/bin/python scripts/scrape_facebook_group_background.py \
  --group-url https://facebook.com/groups/demo \
  --profile-dir /tmp/facebook-background-fixture-profile \
  --fixture tests/fixtures/facebook_group_background.html \
  --output /tmp/facebook-group-background-fixture.csv \
  --rounds 1 --visibility public
```

The optional user-level systemd templates in
[`ops/systemd/`](ops/systemd/) run the same bounded command every six hours.
They are examples only: copy and edit them yourself after the one-time
headed login and a successful fixture/live dry run.  The repository does not
install this timer automatically.

The default `--visibility auto` fails closed when the page does not expose
explicit public/private wording.  After visually confirming that every Group
in the file is public, `--visibility public` records that operator label.  If
the Groups have mixed or unclear visibility, use `--allow-unknown`; the
importer still quarantines those rows unless its explicit governance gate is
supplied.  A private Group additionally requires
`--allow-private`, `--retention-until`, and `--terms-basis-ref`, and those same
values must be passed to the importer.  The browser profile is an
authentication boundary: keep it outside Git, never use another person's
profile, and do not run this against a Group you are not authorised to use.

Record that human decision locally after checking the source page.  The review
command uses one-based data row numbers (the header is not counted), refuses to
edit a row that was already reviewed, and keeps `outreach_status=not_contacted`:

```bash
python scripts/review_property_leads.py \
  --input data/exported/property_owner_coagent_leads.csv \
  --rows 1,3-4 --decision approved --reviewer-id owner-1 \
  --output data/exported/property_owner_coagent_leads_reviewed.csv
python scripts/check_property_capture.py \
  data/exported/property_owner_coagent_leads_reviewed.csv --json
```

Use `--list-pending` to print only row numbers and status counts, or
`--all-pending` to apply one decision to every pending row.  Each write also
appends `property_owner_coagent_review_history.csv` with reviewer metadata and
URL/input hashes; it never copies contact values into the audit file.  An
approved review is evidence for a later, separately authorized outreach step,
not an automatic message permission.

The TG Condo adapter is the first live no-key RSS property source in this lane. It
reads only the site's public condo-rent RSS endpoint (no search-page crawl) and
writes `tgcondo_condo_rent_raw.xml`, `tgcondo_condo_rent.csv`, and
`tgcondo_condo_rent_history.csv`. Run a bounded live sample outside the repo's
runtime data directory:

```bash
mkdir -p /tmp/tgcondo-live-sample
python scripts/scrape_tgcondo_rss.py \
  --limit 5 --output-dir /tmp/tgcondo-live-sample
```

The feed contains listing metadata and usually no owner/co-agent signal, so
those fields remain `unknown` unless the publisher states them explicitly.
The scheduled `tgcondo_condo_rent` job stays disabled while source terms,
raw-result retention, and contact-data handling are reviewed. An optional
contact sample is capped at five public listing pages and requires all three
governance variables (`TGCONDO_CONTACT_STORAGE_APPROVED=1`,
`TGCONDO_RETENTION_UNTIL`, and `TGCONDO_TERMS_BASIS_REF`); it reads visible
agent-card text only and never submits a contact form:

```bash
TGCONDO_CONTACT_STORAGE_APPROVED=1 \
TGCONDO_RETENTION_UNTIL=approved-deletion-deadline \
TGCONDO_TERMS_BASIS_REF=internal-source-review \
python scripts/scrape_tgcondo_rss.py --include-agent-contact --max-contacts 5 \
  --limit 5 --output-dir /tmp/tgcondo-contact-sample
```

The crypto adapter writes the validated raw response to
`data/exported/crypto_prices_raw.json` and the capture projections to
`data/exported/crypto_prices.csv` and `data/exported/crypto_history.csv`.
Lake-first ingestion and the read-only API remain owned by `book-crypto-data`.

The FX adapter writes the validated Frankfurter response to
`data/exported/exchange_rates_raw.json` and the capture projections to
`data/exported/exchange_rates.csv` and `data/exported/exchange_history.csv`.
Lake-first ingestion and the read-only API remain owned by `book-fx-data`.

The stock adapter writes the validated Yahoo Finance chart responses to
`data/exported/stock_prices_raw.json` and the capture projections to
`data/exported/stock_prices.csv` and `data/exported/stock_history.csv`.
Lake-first ingestion and the read-only API remain owned by `book-stock-data`.

The AI tools adapter writes bounded Futurepedia HTML pages to
`data/exported/ai_tools_raw.json` and the capture projections to
`data/exported/ai_tools.csv` and `data/exported/ai_tools_history.csv`. It
validates canonical `/tool/<slug>` URLs and preserves category, rating, pricing,
description, and source attribution for collection-only discovery output.

The DeFi adapter now runs from `book-defi-data`. It writes the validated
DefiLlama response to `book-defi-data/data/exported/defi_yields_raw.json`
and the capture projections to `defi_yields.csv` and
`defi_yields_history.csv`. It uses a Firefox User-Agent, normalizes the
`Optimism` configuration alias to DefiLlama's `OP Mainnet`, requires finite
APY/TVL and unique pool IDs, and rejects stale provider responses.

### Data Freshness Strategy

| Data Type | Frequency | Reason |
|-----------|-----------|--------|
| Discovery feeds | Daily | Trending and time-sensitive sources |
| Jobs | Every 6h | New postings expire quickly |
| Job matching | Daily | Refresh scored opportunities |
| Property | Daily | New listings appear frequently |
| Dashboard | 3 times daily | Keep operational view current |

---

## Quick Start

```bash
# Install dependencies in the repository venv
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Install Playwright browsers (for JS-rendered pages)
playwright install chromium

# Copy config and edit
cp .env.example .env

# Run all due jobs now
python main.py run

# Run a specific configured job
python main.py run job_postings

# Install or inspect the five-minute local scheduler
.\ops\windows\scheduled-task.ps1 install   # Windows (PowerShell)
.\ops\windows\scheduled-task.ps1 status
bash setup_cron.sh install                  # Linux
bash setup_cron.sh status

# Check schedule status
python main.py status

# Run the direct job capture/matching path
python scripts/scrape_job_postings.py
python scripts/filter_job_matches.py

# Run MCP server
python -m mcp_server.server
```

### Board politeness and terms

Every `job_postings` board request goes through `scripts/http_policy.py`: at
most one request per host per `rate_limit` seconds (from `config/jobs.yaml`,
override with `JOB_SCRAPE_MIN_INTERVAL`), and up to three attempts on 429/5xx
or network errors with exponential backoff that honours `Retry-After` (capped
at 60 s). Each run prints its request/retry/failure counts, and the scheduler
records real scraped/new totals.

`config/source_coverage.yaml` records an access type, robots.txt result, and
terms decision for every board. `scripts/source_coverage.py --check` fails if a
board without a decision, or one marked `blocked` (currently `landing-jobs`,
whose robots.txt disallows `/api/`, and `toptal`, which scraped Google), is
scheduled. History (`job_postings_history.csv`) records each job once, on first
sighting.

### Collection health

The collection path is the authoritative default health mode. It checks the
four core artifacts and does not require optional AI enrichment or outbound
notifications:

```bash
python scripts/pipeline_runner.py --health
python scripts/pipeline_health_monitor.py
```

Each scheduled tick (`scripts/scheduled_run.py` on Windows, the cron entry on
Linux) runs `pipeline_health_monitor.py` after each collection run and holds a
non-blocking lock (`scripts/file_lock.py` / `flock`) to prevent overlapping
runs. Each step has its own timeout (collection 45 min, health 5 min — under
the 1 h Task Scheduler limit); a timed-out step is killed with its whole process
tree (`taskkill /T` on Windows, a process group on POSIX) and the tick exits
124, because Windows does not kill children when the task itself is stopped.
`cron.log` is rotated to `cron.log.1` above 5 MB. On Windows, set
`PYTHONUTF8=1` for manual runs; the scheduled runner sets it for you. Use `--send-telegram` only when an
operator has explicitly approved an external notification.

---

## Engine Decision Tree

| Engine | Best For | Speed | Complexity |
|--------|----------|-------|------------|
| **RSS/Atom** | Blogs, news, podcasts | Fastest | Lowest |
| **httpx + BS4** | Static HTML, APIs | Fast | Low |
| **Playwright** | SPAs, JS-rendered, screenshots | Medium | Medium |
| **Selenium** | Complex interactions, legacy sites | Slow | High |
| **Scrapy** | Large crawls (10K+ pages) | Fast | High |

1. Can you get data via RSS/API? → `rss`
2. Is the HTML in source (no JS needed)? → `httpx`
3. Does the page need JS to render? → `playwright`
4. Does the page need login/click/scroll? → `playwright` or `selenium`
5. Need to crawl 10,000+ pages? → `scrapy`

---

## MCP Data-as-a-Service

The `mcp_server/` exposes scraped data as MCP tools via `SearchUseCase`:

| Tool | Description | Data Source |
|------|-------------|-------------|
| `search_jobs` | Search jobs by keyword, location | jobs/ scrapers |
| `search_businesses` | Find businesses by category, area | directories/ scrapers |
| `get_product_prices` | Compare prices across platforms | ecommerce/ scrapers |
| `get_news` | Latest news by topic | news/ scrapers |

### Pricing Model

| Tier | Requests/month | Price | Target |
|------|---------------|-------|--------|
| Free | 100 | ฿0 | Test & demo |
| Starter | 1,000 | ฿499/mo | SMEs, freelancers |
| Pro | 10,000 | ฿2,999/mo | Agencies, startups |
| Enterprise | Unlimited | Custom | Large companies |

---

## Legal Guidelines

### OK to Scrape
- Public business directories (Yellow Pages, Google Maps listings)
- Job boards (public listings)
- RSS feeds
- Public real estate listings
- Product prices (for comparison)

### Be Careful
- Social media (check ToS, rate limit heavily)
- News sites (check robots.txt)
- Review sites (don't republish reviews verbatim)

### Don't Scrape
- Login-required content without permission
- Personal data (PDPA compliance)
- Content behind paywalls
- Anything that violates robots.txt + ToS

---

## Dependencies

See `requirements.txt`. Key packages:
- `httpx` / `requests` — HTTP clients (engines and job scripts)
- `beautifulsoup4` + `lxml` — HTML parsing
- `playwright` — browser automation
- `selenium` — legacy browser automation
- `feedparser` — RSS/Atom parsing
- `pyyaml` — `config/jobs.yaml` loading (built-in scheduler, no APScheduler)

Optional, not in `requirements.txt` (install only when needed):
- `scrapy` — large-scale crawling engine
- `pydantic` — richer validation in `adapters/outbound/utils/validators.py`
  (falls back to plain dataclasses when absent)
- `mcp` — only for `python -m mcp_server.server`

## Tests

```bash
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q          # offline suite under tests/ (pytest.ini)
```

`scripts/test_ats_autoapply.py` is a manual live-network probe and is
deliberately excluded from the suite. CI (`.github/workflows/ci.yml`) runs the
offline suite plus a ruff syntax/undefined-name check on every push.

---

## Job Application Automation Pipeline

> **Safety (2026-08):** Live send/apply is **disabled by default**. See [`SAFETY.md`](./SAFETY.md).
> Paths resolve to this repo’s `data/` directory (not the old monorepo `domains/book-dev/book-scraping` layout).
> `auto_apply.py` only **prepares** drafts (`status=prepared`); it does not submit applications.
> ATS/email live paths require explicit unlock env vars in addition to `--apply` / `--send`.

The job scraping pipeline automates discovery, matching, and application tracking for remote dev jobs.

The targeting policy also has a separate bridge-to-hire lane for
`Contract-to-hire`, `Paid trial`, `Apprenticeship`, `Fellowship`, `Internship`,
and `Volunteer` signals.  A bounded volunteer or open-source contribution is
useful for portfolio, maintainer references, and network—not proof of a job
offer—so it remains `VERIFY`/review-only.  Paid bridge programs can reach
`PASS` only after a human records compensation, scope/duration, mentor,
conversion/reference path, Thailand eligibility, compatible hours, and a
contractor boundary.  Upfront fees, income-share entry, and indefinite unpaid
production work are rejected.

### Data Flow

```
scrape_job_postings.py
    → job_postings.csv (latest snapshot, all sources)
    → config/job_targeting.yaml (contract-first + bridge PASS / VERIFY / REJECT)
    → matched_jobs.csv (PASS first, VERIFY review-only, REJECT excluded)
    → job_descriptions.csv (top matched descriptions, optional enrichment)
    → apply_tracker.csv (via auto_seed_tracker.py, discovered/prepared statuses)
    → resume_variants/ (local application-prep variants)
```

### Supported Job Boards

| Source | Method | Company Extraction |
|--------|--------|-------------------|
| WeWorkRemotely | HTML scrape | Regex + URL slug fallback |
| RemoteOK | API | API field |
| Remotive | API | API field |
| Himalayas | API | API field |
| Jobicy | API | API field |
| Landing.jobs | API | API field + URL slug fallback |
| Arc.dev | API | API field + URL slug fallback |
| Dice | HTML scrape | Regex + context analysis |
| Wellfound | API | API field |
| LinkedIn | Scrape | HTML parsing |

### Company Extraction Strategy

For sources where API/HTML parsing fails, the pipeline uses URL slug extraction as a fallback:

```python
# Example: weworkremotely.com/remote-jobs/proxify-ab-senior-fullstack-developer
# → Extracts "Proxify Ab" by splitting slug and stopping at job keywords
```

The `_extract_company_from_url()` function handles source-specific URL patterns and uses keyword-boundary detection to isolate company names from job titles.

### Data Quality & Backfill

The pipeline includes data quality recovery mechanisms:

- **Backfill from source files**: Missing company/title values are recovered from `matched_jobs.csv` and `job_postings.csv` by URL lookup
- **URL-based extraction**: For rows not in source files, company names are extracted from URL patterns
- **Status-aware recovery**: Rows with `notified` or `applying` status are prioritized for recovery

Latest verified runtime snapshot (2026-08-24; data is gitignored and will
change on the next run):
- `job_postings.csv`: 1,647 rows
- `matched_jobs.csv`: 118 rows
- `apply_tracker.csv`: 106 rows, all seeded as `discovered` (no submission)
- `job_descriptions.csv`: 10 rows
- `resume_variants/`: 5 configured variants

### Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scrape_job_postings.py` | Main scraper — fetches from 10+ job boards |
| `scrape_job_descriptions.py` | Fetches descriptions for top matched jobs |
| `filter_job_matches.py` | Scores and filters the latest postings |
| `auto_seed_tracker.py` | Seeds `apply_tracker.csv` from `matched_jobs.csv` |
| `multi_resume_manager.py` | Initializes and lists application-prep variants |
| `pipeline_runner.py` | Runs collection-mode health and optional pipeline steps |
| `pipeline_health_monitor.py` | Checks disk, scheduler, data freshness, and optional integrations |
| `send_application_emails.py` | Sends application emails to recruiters |
| `auto_send_email.py` | Automated email sending with follow-ups |

The scheduled search uses international remote sources plus Fastwork,
PeoplePerHour, and Toptal. It includes contract-to-hire, paid-trial,
apprenticeship, fellowship, and volunteer discovery keywords without adding a
second scheduler or auto-application path. Generic JobThai/JobBKK full-time
collection is not scheduled. Downstream promotion and draft preparation accept `PASS` only;
live email/ATS submission additionally requires a human-recorded
`application_readiness=APPROVED` and the independent live-send unlock gates.
Each scheduled match refresh also seeds new `PASS` rows into the local tracker
as `discovered`; it does not notify or submit them.

### Running the Pipeline

```bash
# From this repo root, with project venv activated
python scripts/scrape_job_postings.py
python scripts/filter_job_matches.py
python scripts/scrape_job_descriptions.py --top 10
python scripts/auto_seed_tracker.py --min-score 5
python scripts/multi_resume_manager.py --init
python scripts/pipeline_runner.py --health

# Prepare drafts only (does not submit)
python scripts/auto_apply.py --dry-run

# Application emails — dry-run by default; live send is gated (see SAFETY.md)
python scripts/send_application_emails.py
```

---

## Related

- **Lead gen scrapers:** `domains/marketing/growth/book-sales/scripts/` (initial scrapers, being migrated)
- **Facebook scraper:** `domains/product/engineering/book-dev/book-client/scraping-facebook/` (client work)
- **Novel scraper:** `domains/product/engineering/book-dev/book-products/bookreading/ai-service/scrapers.py`
- **Scraping strategy:** `domains/marketing/growth/book-sales/web-scraping-strategy.md`

## Reproducible offline checks

Use a project virtual environment and the committed constraints; both runtime
and test dependencies are pinned in `constraints.txt` (Python 3.11 CI). The
Windows timezone dependency remains conditional in `requirements.txt`.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

`pytest.ini` limits discovery to `tests/` and makes repository imports explicit.
The live ATS probe under `scripts/` is excluded from default test discovery.
To upgrade dependencies, resolve the runtime requirements, pytest, ruff and
tzdata together for Python 3.11, update every affected constraint, and run the
offline suite before committing the new pins.
