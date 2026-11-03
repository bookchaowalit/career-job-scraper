# 09 — ERD (file-based data model)

ไม่มี database server ข้อมูลที่ persist คือไฟล์ CSV/JSON ใต้ `data/` (gitignored) และ JSON schema ใน `contracts/`
"entity" ด้านล่าง = ไฟล์หนึ่งชนิด, "key" = field ที่โค้ดใช้ dedup หรือ join (ส่วนใหญ่คือ `url`)
field ที่แสดงตัดมาเฉพาะที่สำคัญ; รายการเต็มอยู่ใน `fieldnames` ของสคริปต์ที่อ้าง

## Job lane

```mermaid
erDiagram
  JOB_POSTINGS ||--o{ JOB_POSTINGS_HISTORY : "first seen appended"
  JOB_POSTINGS ||--o{ MATCHED_JOBS : "scored by job_match_filter"
  CAREER_POSTINGS ||--o{ MATCHED_JOBS : "supplemental_input"
  MATCHED_JOBS ||--o| JOB_DESCRIPTIONS : "url"
  MATCHED_JOBS ||--o| APPLY_TRACKER : "seed PASS as discovered"
  MATCHED_JOBS ||--o{ REVIEW_PACKET : "application_review build"
  REVIEW_PACKET ||--o| PREPARED_PACKET : "prepare"
  PREPARED_PACKET ||--o| CONFIRMED_APPLICATION : "record-submission"

  JOB_POSTINGS {
    string url PK
    string title
    string company
    string location
    string salary
    string source
    string keyword
    string posted
    string tags
    string scraped_at
  }
  JOB_POSTINGS_HISTORY {
    string url
    string title
    string source
    string scraped_at
  }
  CAREER_POSTINGS {
    string url PK
    string title
    string company
    string source
    string description
    string search_lane
    string scraped_at
  }
  MATCHED_JOBS {
    int rank
    string url PK
    int score
    string qualification_status "PASS VERIFY REJECT"
    string policy_version
    string search_lane
    string employment_type
    string work_arrangement
    string application_readiness
    string qualification_reasons
    string verified_at
  }
  JOB_DESCRIPTIONS {
    string url PK
    string page_title
    string description
    string skills
    string scraped_at
    string status
  }
  APPLY_TRACKER {
    string url PK
    string title
    string company
    string status "discovered prepared ..."
    string note
    string updated_at
    string qualification_status
  }
  REVIEW_PACKET {
    string job_dir PK "career-review dir JOB_ID"
    json candidate_json
    json verification_json
  }
  PREPARED_PACKET {
    string schema_version "prepared-application.v1"
    string status "prepared"
    bool owner_approved
    string created_at
    string candidate_sha256
    string verification_sha256
    string resume_sha256
    string cover_letter_sha256
  }
  CONFIRMED_APPLICATION {
    string url PK "canonical"
    string schema_version "confirmed-application.v1"
    string status "submitted"
    string company
    string title
    string submitted_at
    string followup_date
    string receipt_sha256
    string packet_sha256
  }
```

Sources: `scripts/scrape_job_postings.py` (`save_jobs`, `append_history`), `scripts/career_discovery.py` (`FIELDS`), `scripts/filter_job_matches.py` (`fieldnames`), `scripts/job_target_policy.py` (`HUMAN_VERIFICATION_FIELDS`, `SOURCE_EVIDENCE_FIELDS`), `scripts/scrape_job_descriptions.py`, `scripts/auto_seed_tracker.py` (`POLICY_FIELDS`), `scripts/application_review.py`

## Ops and core stores

```mermaid
erDiagram
  SCHEDULE_STATE ||--|{ JOB_STATE : "one per job name"
  COLLECTION_ITEMS ||--o{ HASH_DB : "content hash"
  SCHEDULE_STATE {
    string file "data/schedule_state.json"
  }
  JOB_STATE {
    string name PK
    string last_run
    int run_count
    int error_count
  }
  COLLECTION_ITEMS {
    string collection PK "data/<collection>/items.json"
    string source
    string url
    string title
    string scraped_at
  }
  HASH_DB {
    string hash PK "data/hash_db.json, MD5"
  }
```

Sources: `adapters/inbound/scheduler_adapter.py`, `adapters/outbound/storage_adapter.py`, `core/models.py`, `core/pipeline/deduplicator.py`, `docs/UPGRADE-PLAN.md` P2 (MD5)

## Property / Facebook Group lane (contracts)

```mermaid
erDiagram
  PROPERTY_CAPTURE {
    string url PK
    string scraped_at
    string title
    string source_channel "listing search social_search"
    string contact_role "owner agent owner_or_agent unknown"
    string co_agent_status "yes no unknown"
    bool contact_public
    string lead_review_status
    string review_decision
    string reviewer_id
    string outreach_status
    string retention_until
    string terms_basis_ref
  }
  PROPERTY_DEMAND {
    string lead_id PK
    string source_url
    string demand_signal
    string contact_permission
    string review_status "call_ready permission_needed needs_more_evidence not_demand"
    string retention_until
  }
  FB_GROUP_POST {
    string post_id PK
    string post_url
    string group_url
    string author_name
    string text
    string visibility "public private unknown"
    bool text_complete
    string capture_method
    string review_decision
    string outreach_status
  }
  SHEET_RAW_POSTS {
    string permalink PK "canonical post URL"
    string collected_at
    string group_name
    string poster
    string text
    bool text_complete
    string processed
  }
  FB_GROUP_POST ||--o| SHEET_RAW_POSTS : "public rows sent by extension"
```

Sources: `contracts/property-capture.v1.json`, `contracts/property-demand.v1.json`, `contracts/facebook-group-post.v1.json`, `integrations/google-sheet/Code.gs` (`HEADER`), `chrome-extension/sheet.js`

## Open questions

- Column contract ของ `job_postings.csv` / `matched_jobs.csv` ที่ `book-job-data` (job.v1) คาดหวังไม่อยู่ใน repo นี้ (`DOCPACK/08-rtm.md` GAP-01)
- `apply_tracker.csv` ยังมี `application_tracker.json` (`scripts/app_tracker.py`, stage `discovered`..`withdrawn`) อีกชุด: ทั้งสองยังใช้งานหรือไม่
