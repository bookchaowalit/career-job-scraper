# 18 — Git & release workflow

รูปแบบที่เห็นจาก `git log origin/main` (90 วัน): ส่วนใหญ่ commit ตรงเข้า `main`; บางงานใช้ branch แล้ว merge ในเครื่อง (`Merge branch '...'`) และมี PR บน GitHub 2 ตัว (#1 squash-merged เป็น `58fcdc6`, #2 merge commit `bb56978`)
ไม่มี tag, release หรือ version ของ repo; production = capture รอบถัดไปที่ checkout `main`

```mermaid
gitGraph
  commit id: "4847903 path safety"
  commit id: "e9fe5b5 polite HTTP"
  branch claude/untitled-session-bhlj06
  checkout claude/untitled-session-bhlj06
  commit id: "ed93e8f atomic stores"
  commit id: "789eb10 docs sync"
  checkout main
  merge claude/untitled-session-bhlj06 id: "9600122"
  commit id: "58fcdc6 PR 1 squash"
  branch fix/telegram-noti-first
  checkout fix/telegram-noti-first
  commit id: "22fa90c noti bot"
  checkout main
  merge fix/telegram-noti-first id: "bb56978 PR 2"
  commit id: "57da436 ext 1.5.0"
  branch feat/scheduled-capture
  checkout feat/scheduled-capture
  commit id: "1b09671 hosted capture"
  checkout main
  merge feat/scheduled-capture id: "43b5eb4"
  commit id: "9ae9c99 uv.lock Sentry"
  commit id: "21c3608 KPI approved"
```

```mermaid
flowchart LR
  A["Change on main or a short branch"] --> B{"Branch?"}
  B -->|"direct"| C["git push origin main"]
  B -->|"branch"| D["Local merge or GitHub PR"]
  D --> C
  C --> E["ci.yml on push main: scraper, windows-scheduler, security"]
  C --> F["Next scheduled-capture run checks out main"]
  F --> G["Capture + ingest to R2 = production effect"]
  E -.->|"not a gate"| F
```

Sources: `git log --first-parent origin/main`, `gh pr list -R bookchaowalit/career-job-scraper --state all`, `.github/workflows/ci.yml`, `.github/workflows/scheduled-capture.yml`

หมายเหตุ: ไม่พบ branch protection ใน repo (ไม่อยู่ในไฟล์); `origin` ยังมี branch `claude/untitled-session-bhlj06` และ `fix/telegram-noti-first` ค้างอยู่

## Open questions

- มี branch protection / ruleset บน `main` หรือไม่ (ตรวจจาก repo ไม่ได้)
- ควรลบ remote branch ที่ merge แล้ว 2 ตัวหรือไม่
