# 11 — State machines

entity ที่มี status / lifecycle field ในโค้ด

## 1. Job qualification (matched_jobs.csv `qualification_status`)

```mermaid
stateDiagram-v2
  [*] --> Scored: job_match_filter score
  Scored --> PASS: policy satisfied
  Scored --> VERIFY: needs human evidence, e.g. volunteer or internship
  Scored --> REJECT: Thai full-time, onsite or hybrid, exclusivity in remote_contract
  VERIFY --> PASS: verification complete, verified_at within verification_max_age_days default 7
  PASS --> VERIFY: verified_at too old
  REJECT --> [*]: not written, include_statuses is PASS and VERIFY
```

Sources: `scripts/job_target_policy.py`, `scripts/filter_job_matches.py`, `config/jobs.yaml` (`include_statuses`), `DOCPACK/05-srs.md` US-04, US-06

## 2. Application (apply_tracker.csv → prepared.json → confirmed_applications.json)

```mermaid
stateDiagram-v2
  [*] --> discovered: auto_seed_tracker, PASS only
  discovered --> packet: application_review build
  packet --> prepared_approved: prepare --owner-approved, hashes stored
  packet --> prepared: prepare without approval, hashes stored
  prepared --> [*]: not approved, nothing sent; a second prepare in the same directory fails with Prepared packet already exists, so approval needs a new review directory
  prepared_approved --> submitted: record-submission with receipt
  submitted --> followup_due: followup_date = submitted_at + 7 days
```

`auto_apply.py` เขียนได้แค่ `prepared`; `submitted` เกิดได้จาก `record_submission` เท่านั้น
packet ที่ prepare แล้วแก้ไม่ได้: ต้องสร้าง review directory ใหม่

Sources: `scripts/auto_seed_tracker.py`, `scripts/application_review.py`, `scripts/safety.py` (`is_prepared`, `is_submitted`), `SAFETY.md`

Tracker เก่าอีกชุด (`scripts/app_tracker.py` → `data/application_tracker.json`) มี stage: `discovered`, `saved`, `applied`, `screening`, `technical`, `onsite`, `offer`, `accepted`, `rejected`, `withdrawn` (ไม่ได้ตรวจว่ายังใช้งาน)

## 3. Property / Facebook Group lead review

```mermaid
stateDiagram-v2
  [*] --> pending: import, outreach not_contacted
  pending --> approved: reviewer with reviewer_id
  pending --> rejected: reviewer
  pending --> needs_more_evidence: reviewer
  needs_more_evidence --> pending: new evidence
  approved --> approved_to_contact: outreach gate
  approved_to_contact --> contacted: manual outreach
  contacted --> opt_out
  approved_to_contact --> opt_out
```

`outreach_status` enum: `not_contacted`, `approved_to_contact`, `contacted`, `opt_out`; `review_decision` enum: `pending`, `approved`, `rejected`, `needs_more_evidence`
SRS: reviewer ไม่สามารถเลื่อนเป็น `approved_to_contact` เองได้ (`DOCPACK/05-srs.md` §1)

Sources: `contracts/property-capture.v1.json`, `contracts/facebook-group-post.v1.json`, `scripts/check_property_social_capture.py`, `scripts/review_facebook_group_posts.py`, `SAFETY.md`

## 4. Scheduled job (ScrapeJob)

```mermaid
stateDiagram-v2
  [*] --> disabled: enabled false in jobs.yaml
  [*] --> waiting: enabled true
  disabled --> waiting: main.py enable
  waiting --> disabled: main.py disable
  waiting --> due: never run, or interval since last_run passed
  due --> running: tick picks job
  running --> waiting: mark_completed, last_run updated
```

Sources: `core/models.py` (`ScrapeJob.is_due`), `adapters/inbound/scheduler_adapter.py`, `main.py`

## Open questions

- ใครเป็นผู้เลื่อน `approved` → `approved_to_contact` ได้ และมีสคริปต์ใดเขียนสถานะ `contacted` (ไม่พบในรอบนี้)
- transition `prepared` → `prepared_approved` จริงคือ field `owner_approved` ใน packet ใหม่ (packet เดิมแก้ไม่ได้): ต้องสร้าง review dir ใหม่เพื่อ approve หรือไม่
