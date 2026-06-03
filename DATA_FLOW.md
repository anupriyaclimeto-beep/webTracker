# Data Flow & Storage Explanation

## Current System (Today)

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────┐
│                    CRAWLER (crawler.py)                  │
│  Runs locally or on GitHub Actions (4:30 PM UTC)         │
└────────────────────┬────────────────────────────────────┘
                     │ Takes screenshots, HTML, HAR files
                     ▼
┌─────────────────────────────────────────────────────────┐
│               STORAGE LAYER (storage.py)                 │
│  Saves artifacts locally OR uploads to Cloudinary        │
└────────┬──────────────────────────────────┬─────────────┘
         │                                  │
         ▼                                  ▼
    LOCAL FILES                       CLOUDINARY (Optional)
  archive/ folder                   Cloud image/file storage
  - screenshot.png                  (returns public URLs)
  - snapshot.html
  - network.har
         │                                  │
         └──────────────────┬───────────────┘
                            │
                     ▼ Store URLs/paths
         ┌─────────────────────────────┐
         │    DATABASE (SQLite or      │
         │       Supabase Postgres)    │
         └──────────────┬──────────────┘
                        │
         ┌──────────────┴──────────────┐
         │                             │
         ▼                             ▼
    CHANGES TABLE                BASELINES TABLE
  - What changed                - Previous versions
  - Diff details                - Comparison snapshots
  - Timestamps
         │
         └─────────────────────┬──────────────────┐
                               │                  │
                               ▼                  ▼
                         ┌─────────────┐   ┌─────────────┐
                         │ Streamlit   │   │ GitHub      │
                         │ Cloud UI    │   │ Actions     │
                         │ (app.py)    │   │ (cron)      │
                         └─────────────┘   └─────────────┘
                               │                  │
                               └────┬─────────────┘
                                    │ Read data
                                    │ (polling every 5s)
```

---

## Database Options

You have TWO database backends:

### Option 1: SQLite (Local) ← **Currently Active by Default**

**Database File:** `changes.db` (local file)

**Pros:**
- ✅ Works offline
- ✅ No credentials needed
- ✅ Works on Streamlit Cloud (files stored in `/tmp/`)

**Cons:**
- ❌ Data lost if server restarts (Streamlit Cloud)
- ❌ Can't share between crawler (GitHub Actions) and UI (Streamlit Cloud)
- ❌ Concurrent access issues

**Storage:**
```
changes.db (SQLite file)
  └─ changes table        (what changed on each page)
  └─ baselines table      (previous snapshots for comparison)
  └─ crawl_log table      (crawl history & status)
```

---

### Option 2: Supabase Postgres (Remote) ← **Recommended for Live**

**Database:** PostgreSQL on Supabase cloud

**Activation:** Set env vars:
```bash
SUPABASE_HOST=your-project.supabase.co
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=<your-password>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

**Pros:**
- ✅ Data persists on Supabase servers (not lost on restart)
- ✅ Crawler (GitHub Actions) and UI (Streamlit Cloud) can both read/write
- ✅ Real-time updates
- ✅ Backups automatically managed by Supabase

**Cons:**
- ❌ Requires network connection
- ❌ Need Supabase account & credentials

**Storage:**
```
Supabase PostgreSQL
  └─ public.changes table        (what changed)
  └─ public.baselines table      (snapshots for comparison)
  └─ public.crawl_log table      (crawl history)
```

---

## File Storage (Artifacts)

### Local (Default)
```
archive/
  ├─ EPR PLASTIC/
  │  ├─ eprplastic.cpcb.gov.in_plastic_home/
  │  │  ├─ 20260603_101500/
  │  │  │  ├─ screenshot.png      ← Before/after image
  │  │  │  ├─ snapshot.html       ← Full HTML for diff comparison
  │  │  │  └─ network.har         ← Network requests log
  │  │  ├─ 20260602_143000/
  │  │  │  └─ ...
```

**Problem on Streamlit Cloud:** Files stored in `/tmp/` are deleted when app restarts!

### Cloudinary Cloud (Optional)
If you set Cloudinary credentials:
```
Cloudinary Cloud Storage
  └─ webtracker/
     ├─ screenshots/
     │  └─ eprplastic_cpcb.../screenshot.png → https://res.cloudinary.com/...
     ├─ html/
     │  └─ eprplastic_cpcb.../snapshot.html  → https://res.cloudinary.com/...
```

---

## Data Flow Example

### Step 1: Crawler Runs (GitHub Actions 4:30 PM UTC)
```python
crawler.py
  │
  ├─ Navigate to https://eprplastic.cpcb.gov.in
  ├─ Take screenshot → screenshot.png
  ├─ Extract HTML → snapshot.html
  ├─ Record network requests → network.har
  │
  └─ Call: archive_artefacts(
       portal="EPR PLASTIC",
       url="https://eprplastic.cpcb.gov.in/#/plastic/home",
       screenshot_bytes=<PNG>,
       html_content=<HTML>,
       har_data=<JSON>
     )
```

### Step 2: Storage.py Saves Files
```python
archive_artefacts()
  │
  ├─ Create folder: archive/EPR PLASTIC/eprplastic.cpcb.gov.in.../20260603_143000/
  ├─ Save screenshot.png locally (and upload to Cloudinary if enabled)
  ├─ Save snapshot.html locally (and upload to Cloudinary if enabled)
  ├─ Save network.har locally
  │
  └─ Return paths:
     - html_path = "archive/EPR PLASTIC/.../snapshot.html"
     - screenshot_path = "archive/EPR PLASTIC/.../screenshot.png"
     - screenshot_url = "https://res.cloudinary.com/..." (if Cloudinary)
     - html_url = "https://res.cloudinary.com/..." (if Cloudinary)
```

### Step 3: Database Records Created
```python
update_baseline(
  portal="EPR PLASTIC",
  url="https://eprplastic.cpcb.gov.in/#/plastic/home",
  html_path="archive/EPR PLASTIC/..../snapshot.html",
  screenshot_path="archive/EPR PLASTIC/..../screenshot.png",
  har_path="archive/EPR PLASTIC/..../network.har",
  screenshot_url="https://res.cloudinary.com/...",  # if uploaded
  html_url="https://res.cloudinary.com/...",        # if uploaded
)
```

**Inserted into `baselines` table:**
```
id: 123
portal: "EPR PLASTIC"
url: "https://eprplastic.cpcb.gov.in/#/plastic/home"
html_path: "archive/EPR PLASTIC/.../snapshot.html"
screenshot_path: "archive/EPR PLASTIC/.../screenshot.png"
screenshot_url: "https://res.cloudinary.com/.../screenshot.png"
updated_at: "2026-06-03T16:30:00"
```

### Step 4: Diff Detection
```python
diff_and_store()
  │
  ├─ Load previous baseline from database
  ├─ Compare current HTML vs previous HTML
  ├─ Compare current screenshot vs previous screenshot
  ├─ Detect differences (text added/removed, visual changes)
  │
  └─ save_diff(
       portal="EPR PLASTIC",
       url="https://eprplastic.cpcb.gov.in/#/plastic/home",
       diff_type="html",
       diff_detail={
         "changed": true,
         "summary": "Button 'Submit' added",
         "diff_lines": 12,
         ...
       },
       screenshot_url="https://res.cloudinary.com/..."  # if available
     )
```

**Inserted into `changes` table:**
```
id: 456
portal: "EPR PLASTIC"
url: "https://eprplastic.cpcb.gov.in/#/plastic/home"
diff_type: "html"
diff_detail: {"changed": true, "summary": "Button 'Submit' added", ...}
timestamp: "2026-06-03T16:30:45"
screenshot_url: "https://res.cloudinary.com/.../screenshot.png"
```

### Step 5: Streamlit UI Reads Data
```python
app.py (Streamlit Cloud)
  │
  ├─ Query database: SELECT * FROM changes ORDER BY timestamp DESC
  │
  ├─ For each change:
  │  ├─ Show summary: "Button 'Submit' added"
  │  ├─ Load screenshot URL (from Cloudinary or local path)
  │  ├─ Compare with previous baseline
  │  ├─ Show inline highlights in HTML diff
  │  └─ Display before/after screenshots
  │
  └─ User sees all detected changes in browser
```

---

## Current Status (Your System)

| Component | Status | Location |
|-----------|--------|----------|
| **Database** | SQLite (local) | `changes.db` |
| **Files** | Local directory | `archive/` |
| **Cloud upload** | Cloudinary (if configured) | Env vars |
| **Crawler** | GitHub Actions @ 4:30 PM UTC | `.github/workflows/cron-crawler.yml` |
| **UI** | Streamlit Cloud | Deployed |
| **Data sync** | Polls every 5s | `app.py` line 1302 |

---

## Problem on Streamlit Cloud

When the Streamlit Cloud app restarts:
- ❌ Local SQLite database (`changes.db`) is deleted
- ❌ Local archive files (`archive/`) are deleted
- ❌ All historical data is lost

---

## Recommendation for Live

Use **Supabase Postgres** + **Cloudinary**:

```
GitHub Actions (crawler)
  ├─ Run at 4:30 PM UTC
  ├─ Save files to Cloudinary → get public URLs
  ├─ Insert records to Supabase Postgres
  │
Streamlit Cloud (UI)
  ├─ Query Supabase Postgres
  ├─ Display screenshots from Cloudinary URLs
  ├─ No local files needed
  └─ Data persists across restarts
```

**Result:**
- ✅ Data never lost
- ✅ Works on Streamlit Cloud
- ✅ Crawler and UI can share same database
- ✅ Files accessible globally (Cloudinary URLs)

---

## Next Steps

1. **Keep SQLite locally** (works for local testing)
2. **Migrate to Supabase + Cloudinary** when deploying to live
3. Set environment variables in Streamlit Cloud dashboard

Want me to implement the Supabase + Cloudinary migration?
