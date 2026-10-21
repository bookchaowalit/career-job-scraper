# International career application workflow

This workflow supports three distinct lanes:

- `remote_contract`: compatible side engagements under the existing policy.
- `remote_career`: changing employment while working remotely from Thailand.
- `relocation`: changing employment and moving to the destination country.

Full-time commitment is a review item for a career change, not an automatic
rejection for holding two jobs. Relocation does not require Thailand remote
eligibility. It does require source-backed destination work authorization,
employment terms and a reviewed transition/notice period. A visa keyword is
only a signal; a sponsorship question or search query is not evidence.

## Collection and shortlist

`config/career_sources.yaml` lists bounded public company boards. The adapter
uses GET-only [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
requests with full posting content; no ATS API key or applicant data is used.
It fails without replacing the last capture when any board request fails.
An empty successful response is different from an unavailable source.

```bash
.venv/bin/python scripts/career_discovery.py --write
.venv/bin/python scripts/filter_job_matches.py --supplemental-input data/career_postings.csv --top 0
.venv/bin/python scripts/application_review.py build --per-lane 3
```

Review `data/career-review/current/README.md`. Each packet contains the exact
candidate snapshot, Thai review checklist and blank `verification.json`.
Existing snapshots are preserved; create another `--output` directory to
refresh a previously reviewed listing. Data and applicant material stay in
ignored local storage. No draft is recorded as submitted.

The existing due-job scheduler includes `career_postings` before
`job_match_filter` on the six-hour schedule. The filter merges the capture
with the existing job postings, deduplicates URLs and retains lane/description
evidence in `matched_jobs.csv`. The unchanged book-job-data ingest preserves
those additive fields in Bronze `job.v1/job_matches`. Local capture success
does not prove the hosted API has ingested the new snapshot. The hosted
`scheduled-capture` workflow (see `RUNBOOK.md`) runs the same three steps
every 6 hours and ingests the result into R2; it never builds review packets
or touches the apply tracker.

## Review and prepare

Choose one packet and fill `verification.json` using current source evidence:

- Common: `verified_role_requirements=YES` (skills, experience and languages),
  `verified_employment_type`, `verified_career_transition=YES`,
  `verified_employment_terms=YES`, `verification_source_url`, `verified_at`
  (`YYYY-MM-DD`), and `verification_notes`.
- Remote: `verified_work_arrangement=Remote` and
  `verified_thailand_eligibility=YES`.
- Relocation: `verified_destination_country` and `verified_destination_eligibility=YES`, based on actual work
  rights or the employer's sponsorship pathway, not willingness to move.

Verification must be no more than seven days old and not future-dated.
Prepare a truthful tailored resume and cover letter in private local files.
Do not fill unknown salary, notice period, identity, legal declarations,
demographics, or company-specific questions with guessed answers.

```bash
.venv/bin/python scripts/application_review.py prepare \
  --directory data/career-review/current/JOB_ID \
  --resume /private/path/resume.pdf \
  --cover-letter /private/path/cover-letter.md
```

Only add `--owner-approved` when the owner has reviewed this exact job and
both documents and authorized submission. This command still does not send.
It writes `prepared.json` with document/candidate/verification hashes. A
prepared packet is immutable; use a new review directory for revisions.

## Submit and retain evidence

Use the job's official application URL and manually review the ATS form.
Manual submission is the supported cross-ATS route, including Lever and
Ashby. The legacy automated Lever adapter is incomplete, and generic browser
automation is not certified by this workflow. Live sending remains disabled
by default; no cron submits applications.

After a real submission, save the ATS confirmation or sent-message receipt
privately. The following is an operator attestation with retained evidence,
not an automated authenticity check of a screenshot or message:

```bash
.venv/bin/python scripts/application_review.py record-submission \
  --packet data/career-review/current/JOB_ID/prepared.json \
  --receipt /private/path/confirmation.pdf \
  --submitted-at YYYY-MM-DDTHH:MM:SS+07:00
```

The command requires the owner-approved packet, unchanged documents and a
nonempty receipt. It writes `data/confirmed_applications.json`, deduplicates
the job URL under a file lock, and assigns a follow-up seven days later.
It does not infer success because an ATS form disappeared.

From the parent Solo Empire repository, preview the metadata-only handoff:

```bash
python3 infra/scripts/opportunities/import_job_applications.py \
  --input /absolute/path/to/book-job-scraping/data/confirmed_applications.json
```

Add `--apply` to append confirmed rows to
`opportunities/applications/JOB-TRACKER.md`. Raw receipts and applicant
documents are not copied to that tracker. The export is local operational
metadata, not a new raw-data API or database projection.

## Verification

```bash
.venv/bin/python -m unittest tests/test_career_pipeline.py tests/test_job_target_policy.py tests/test_paths_and_safety.py tests/test_source_coverage.py -q
```

The fixture E2E covers capture → match → review → prepare → receipt ledger,
including incomplete qualification, stale approvals, modified documents and
duplicate recording. It never sends a real application. The parent import
tests live in `infra/tests/data_lake/job_application_import_test.py`.
