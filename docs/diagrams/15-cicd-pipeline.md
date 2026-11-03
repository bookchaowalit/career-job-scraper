# 15 — CI/CD pipeline

สอง workflow ใน `.github/workflows/`: `ci.yml` (quality + security gate) และ `scheduled-capture.yml` (production run = capture + publish)
ไม่มี workflow ที่ "deploy code": capture รอบถัดไป checkout `main` ล่าสุดเอง

```mermaid
flowchart TD
  subgraph CI["ci.yml: push main, pull_request, workflow_dispatch; concurrency ci-ref, cancel in progress"]
    T1(["trigger"]) --> J1["scraper: platform-ci-workflows ci-python.yml v1.1.1"]
    T1 --> J2["windows-scheduler: windows-2025, 10 min"]
    T1 --> J3["security: platform-ci-workflows security.yml v1.1.1"]
    J1 --> J1a["Checkout, uv + Python 3.11, install"]
    J1a --> J1b["Lint Ruff"]
    J1b --> J1c["Typecheck: mypy"]
    J1c --> J1d["Test: pytest -q --cov, offline"]
    J1d --> J1e["Coverage gate 46%"]
    J2 --> J2a["pip install pytest with constraints.txt"]
    J2a --> J2b["pytest test_file_lock, test_scheduled_run, test_atomic_writes"]
    J3 --> S1["gitleaks"]
    J3 --> S2["semgrep"]
    J3 --> S3["osv-scanner"]
    J3 --> S4["trivy-fs"]
  end

  subgraph CAP["scheduled-capture.yml: cron 17 */6 * * *, workflow_dispatch; concurrency scheduled-capture, no cancel; 30 min"]
    C0(["trigger"]) --> C1["checkout, setup-python 3.11, setup-uv 0.13.1"]
    C1 --> C2["Install scraper: uv sync --frozen --no-dev"]
    C2 --> C3["Install book-job-data at BOOK_JOB_DATA_REF in separate venv"]
    C3 --> C4["Restore capture history cache"]
    C4 --> C5["Capture: cloud_capture.py, SENTRY_DSN"]
    C5 --> C6["Save capture history, if not cancelled"]
    C6 --> C7["Ingest into R2, if not cancelled"]
    C7 --> C8["Heartbeat, always"]
  end

  CI -.->|"no needs link, main is read by next scheduled run"| CAP
```

Sources: `.github/workflows/ci.yml`, `.github/workflows/scheduled-capture.yml`, `bookchaowalit/platform-ci-workflows` `.github/workflows/ci-python.yml` and `security.yml` at `87dc5e1c` (job and step names read via `gh api`), `pytest.ini`, `ruff.toml`, `pyproject.toml`, `constraints.txt`, `renovate.json`

หมายเหตุ: CI ไม่ได้เป็น gate ของ capture: ถ้า CI แดงบน `main`, capture รอบถัดไปก็ยังรันโค้ดนั้น (ไม่มี `needs` หรือ `workflow_run`)

## Open questions

- ต้องการให้ capture รันเฉพาะ SHA ที่ CI เขียวหรือไม่
- `tests/js/*.test.js` รันใน CI หรือไม่: `tests/test_chrome_extension_cloud_upload.py` เรียก `node --test` แบบ `skipUnless(node)` ขึ้นกับว่า runner ของ shared workflow มี node
- Renovate (`renovate.json`) เปิด PR จริงบน repo นี้หรือไม่ (ไม่พบ PR ใน `gh run list` ช่วงนี้)
