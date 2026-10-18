# book-job-scraping — Safety & P0 Status

**Status:** collection scheduler active; **not production-ready** for live applications.
**Last updated:** 2026-09-14

**Property/social lane update (2026-09-14):** Property owner, agent, and
co-agent signals are extracted only from explicit public listing or search
metadata.  Social discovery is held behind the official Brave Search API and
an explicit result-storage approval gate; the collector never logs into or
crawls Facebook, Instagram, TikTok, or LINE.
Every capture row starts as `review_decision=pending` and
`outreach_status=not_contacted`; the redacted
`scripts/check_property_social_capture.py` validator requires reviewer
metadata before an outreach state can advance.
The `scripts/scrape_property_social.py --fixture` path is a synthetic offline
smoke test only; it does not contact a source, unlock the scheduler, or grant
permission to retain live search results.

The free owner/co-agent path is a user-provided browser export.  The included
Chrome extension reads only the rendered text of the active tab after the
operator clicks capture, stores it in local extension storage, and downloads a
CSV on request.  `scripts/import_property_leads.py` then applies an HTTPS
source allowlist, explicit owner/co-agent evidence rules, canonical URL and
listing-fingerprint deduplication, and a redacted quarantine report.  It does
not fetch listing URLs, read cookies, authenticate to social networks, inspect
private groups, or send outreach.  The extension and importer are not a
permission to collect data from a source that disallows the user's use.

The Facebook Group lane applies the same local-only boundary at post level.
The extension reads currently rendered `[role="article"]` nodes and their
permalinks, lets the operator label `public`, `private`, or `unknown`, and
never calls a Facebook API, opens another post, or exports cookies.  Since 1.5.0
it can also scroll, but only as an operator-started **Auto-scroll capture** in
the Group tab the operator has open: one screen per step with a fixed 4 s wait
(no randomised, human-mimicking timing), expanding visible "See more" controls,
and stopping at 40 posts or 5 minutes by default (hard caps 200 / 15), after
three steps with nothing new, at an already-saved post, on leaving the group,
or on Stop.  There is no scheduler and no background tab.  Results land in the
capture draft; visibility labelling, Save, and any Sheet send stay manual.
Automated scrolling may still conflict with Facebook's terms and puts the
operator's own account at risk; that is the operator's decision.
`scripts/import_facebook_group_posts.py` recomputes post identity, extracts
owner/co-agent evidence from supplied text, keeps public rows review-only, and
quarantines private/unknown rows unless an explicit gate, retention deadline,
and terms-basis reference are present.  `contact_public` is derived from the
operator's visibility label and cannot be asserted by input data.  The
`facebook.group-post.v1` snapshot is not a CRM or outreach permission.

The extension's optional cloud upload (off by default, see README) sends only
the CSV the operator just exported to a storage account the operator signed
into: Google Drive (`drive.file`), Dropbox (app folder), or OneDrive (app
folder).  It never sends cookies, page HTML, or anything to Facebook, and
access tokens stay in memory-only session storage.  An uploaded copy is still
subject to the same visibility, retention, and terms-basis rules as the local
file: private or `unknown` Group rows must not be uploaded to a shared folder,
and deleting a capture means deleting the cloud copy too.

Since 1.4.0 the extension holds no `<all_urls>` permission: its page script is
injected only into the tab where the operator opens the popup, or runs on the
listed job boards.  Post URLs are canonicalised without Facebook's per-load
`__cft__`/`__tn__` tokens, identically in the extension, the importer, and
`Code.gs`.

The optional Google Sheet sink sends only `public`-labelled Group rows the
operator saved or exported, to an Apps Script web app the operator deployed in
their own Sheet, authenticated by a shared secret.  It does not change the
capture boundary above: the extension reads only what is rendered in the tab
the operator opened, scrolling only during an operator-started auto-scroll
capture.  The Sheet is a copy of personal
data (poster names, post text that may contain phone numbers), so the same
purpose, retention, and deletion duties apply to it as to the local CSV.
Exported CSV cells that start with `= + - @` get a leading `'` so spreadsheets
do not execute them; both importers strip that guard on read.

The opt-in `scripts/scrape_facebook_group_background.py` is a local Playwright
alternative for an operator who does not want the extension.  It requires a
dedicated profile directory outside the repository, never uses the default
personal Chrome profile, and never calls `context.cookies` or exports
`storage_state`.  The profile may contain a login session, so filesystem access
to it is itself sensitive.  The script accepts only canonical Facebook Group
URLs from a local list, bounds scroll rounds and output rows, keeps the Group
identity check, and writes only rendered post fields.  It is not part of the
cron schedule and does not auto-login, bypass a checkpoint, follow post links,
or send outreach.  A page with unknown visibility is skipped unless the
operator explicitly supplies `--allow-unknown` or an operator-confirmed
`--visibility public|private|unknown` label.  `--visibility public` must only
be used after checking every Group in the input list.  Private capture
additionally requires retention and terms-basis flags and remains quarantined
by the importer until governance is recorded.
The `--fixture tests/fixtures/facebook_group_background.html` mode is an
offline browser smoke only: document requests are fulfilled from that local
synthetic file and other requests are aborted.  Optional user-level timer
templates live under `ops/systemd/`; they are not installed automatically.

The importer writes local raw input bytes plus a checksum manifest so a run is
replayable, but the output remains a review queue rather than a CRM write.
Accepted rows always start with `review_decision=pending` and
`outreach_status=not_contacted`; source terms, privacy purpose, retention, and
any contact approval must be decided before a downstream handoff.

Use `scripts/review_property_leads.py` to record that decision after a human
checks the source page.  It updates only pending rows, requires a reviewer ID,
stores the decision and timestamp, appends a hash-only audit file, and keeps
`outreach_status=not_contacted`.  It never promotes a row to `approved_to_contact`
or sends a message.

The source review keeps the lane gated: [Brave Search API Terms of
Use](https://api-dashboard.search.brave.com/documentation/resources/terms-of-service)
restrict storing Search Results unless the subscribed plan grants storage
rights; [Meta's scraping guidance](https://www.facebook.com/help/463983701520800)
distinguishes authorized crawling from automated collection that violates its
terms; and the [Thai PDPC privacy
notice](https://gppc.pdpc.or.th/wp-content/uploads/GPPC-PDPC_Register_Privacy-Notice-%E0%B8%89%E0%B8%9A%E0%B8%B1%E0%B8%9A%E0%B8%A2%E0%B9%88%E0%B8%AD_05062024.pdf)
shows that contact data needs a stated purpose, legal basis, retention, and
deletion path.  These checks do not authorize platform crawling or outreach.

The property lane also has a bounded TG Condo RSS adapter. It reads the public
condo-rent feed only; the scheduler remains disabled until TG Condo terms,
retention, and any public-contact storage basis are recorded. RSS rows do not
prove ownership or co-agent willingness. Optional agent-card enrichment is
capped at five pages, requires explicit governance variables, and never posts
or submits a contact form.

**Career workflow update (2026-09-07):** See [CAREER-WORKFLOW.md](CAREER-WORKFLOW.md).
The onsite/Thailand/concurrent-employment exclusions below apply to the
`remote_contract` lane. Career changes have separate source-backed eligibility
and transition checks. New packets support reviewed manual ATS submission and
receipt metadata handoff; they do not certify or unlock the legacy senders.

## Correct operating statement

- This repository's collection scheduler is explicitly installed and active
  every five minutes via `ops/windows/scheduled-task.ps1` (Windows host) or
  `setup_cron.sh` (Linux).
- The cron runs only due collection jobs, then the health monitor, under a
  `flock` lock. It does not send applications or write the Solo Empire DB.
- Live email/ATS send paths exist but are **blocked by default**.

## P0 fixes applied

1. **Paths** — scripts resolve `REPO_ROOT` / `data/` / `scripts/` from this repo (`scripts/repo_paths.py`), not `domains/book-dev/book-scraping`.
2. **Dependencies** — use project venv + `requirements.txt`; scripts must not `pip install` at runtime.
3. **Send gates** — live send/apply requires:
   - CLI flag (`--send` or `--apply`)
   - `BOOK_JOB_LIVE_SEND_ENABLED=1`
   - `BOOK_JOB_SEND_UNLOCK=I_UNDERSTAND_LIVE_SEND`
4. **`--test` safety** — `ats_auto_apply.py --test` is preview-only (never opens Chrome / never submits).
5. **Status semantics** — draft generators write `prepared` (legacy `auto_applied` is treated as prepared on read). `submitted` is for real sends only.
6. **Scheduler safety** — cron uses the repository `.venv`, prevents overlap
   with `flock`, and runs `pipeline_health_monitor.py` after collection.
7. **Contract-first qualification** — `config/job_targeting.yaml` classifies
   every match as `PASS`, `VERIFY`, or `REJECT`. Thai full-time, geo-ineligible,
   onsite/hybrid, exclusivity, and explicit Thai employee/social-security
   listings cannot reach promotion or preparation.
8. **Submission approval** — live email/ATS paths additionally require
   `qualification_status=PASS` and `application_readiness=APPROVED`. The
   existing CLI + two environment unlock gates still apply after that check.
9. **Bridge-to-hire safety** — volunteer/internship signals remain
   `VERIFY`/review-only; paid bridge programs require human evidence for
   compensation, bounded scope/duration, mentor, and conversion/reference path.
   Upfront-fee, income-share-entry, and indefinite unpaid production signals
   are rejected.

## Do not do (until explicitly ordered)

- Do not run `send_application_emails.py --send`
- Do not run `email_application.py --send` or batch `--no-dry-run`
- Do not run `auto_send_email.py --send`
- Do not run `send_followup_emails.py --send`
- Do not run `ats_auto_apply.py --apply`
- Do not enable live send/apply or set the unlock env vars casually.
- Do not mark `application_readiness=APPROVED` until contract, current-employer
  conflict, hours/timezone, IP/confidentiality, tax, and payroll/EOR terms have
  been reviewed.
- `setup_cron.sh` is collection-only; use `setup_cron.sh remove` to pause this
  repository's scheduler.
- Do not set `BRAVE_SEARCH_STORAGE_APPROVED=1` until the subscribed Brave plan
  grants storage rights and the platform terms/PDPA purpose, retention, and
  human-review process are documented. The social job remains disabled by
  default.

## Local setup

```bash
cd path/to/book-job-scraping
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# optional lighter test deps only:
# pip install httpx pyyaml

# smoke
.venv/bin/python scripts/pipeline_runner.py --dry-run
.venv/bin/python scripts/pipeline_runner.py --health
.venv/bin/python scripts/auto_apply.py --dry-run
.venv/bin/python scripts/ats_auto_apply.py --test
.venv/bin/python -m unittest tests/test_paths_and_safety.py -v
.venv/bin/python -m unittest tests/test_job_target_policy.py -v
```

## Current verification

On 2026-08-24, the collection health check passed with fresh core artifacts:
`job_postings.csv`, `matched_jobs.csv`, `apply_tracker.csv`, and
`job_descriptions.csv`. Optional OpenRouter enrichment and Telegram alerts are
not required for collection health and remain disabled unless explicitly
configured.

Runtime data lives in `./data/` (gitignored except `.gitkeep`).

## Tracker dual-write note (P1)

| Tracker | Role |
|---|---|
| `data/apply_tracker.csv` | Legacy nested pipeline tracker |
| Solo Empire `opportunities/applications/JOB-TRACKER.md` | Canonical submitted-applications record |

Use `application_review.py` and the parent's `import_job_applications.py` for
the confirmed-receipt handoff. The legacy tracker is not automatically migrated;
old `applied`/`sent` labels alone are not confirmed submission evidence.
