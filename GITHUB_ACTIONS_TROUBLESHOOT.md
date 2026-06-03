# GitHub Actions Cron Job Troubleshooting

## Step 1: Check GitHub Actions Logs

1. Go to your repo on GitHub
2. Click **Actions** tab
3. Click **"Scheduled Crawler (4:30 PM UTC)"**
4. Find the failed run
5. Click it and expand **"Run crawler for all portals"** to see full logs

## Step 2: Common Errors & Fixes

### Error: "ModuleNotFoundError: No module named 'playwright'"
- Playwright not installed in GitHub Actions
- **Fix:** Already handled in workflow (runs `playwright install`)

### Error: "Auth failed" or "Page timeout"
- Portal URL unreachable or requires specific headers
- **Fix:** Test locally first:
  ```bash
  python scripts/test_crawler.py "EPR PLASTIC"
  ```

### Error: "Supabase connection refused"
- Environment variables not set in GitHub
- **Fix:** 
  1. Go to repo → Settings → Secrets and variables → Actions
  2. Verify `SUPABASE_HOST`, `SUPABASE_PORT`, `SUPABASE_DB`, `SUPABASE_USER`, `SUPABASE_PASSWORD` are set

### Error: "No such file or directory: config.json"
- Working directory is wrong
- **Fix:** Already handled in workflow (runs from repo root)

### Error: "Cloudinary upload failed"
- Cloudinary credentials missing
- **Fix:**
  1. Check if `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` are set
  2. If not set, it will fall back to local storage (OK for now)

---

## Step 3: View GitHub Actions Logs

Look for these patterns in the logs:

**✅ Good (crawler ran):**
```
Starting crawl for portal: EPR PLASTIC (crawl_id=123)
Home page done ✓ | pages_visited=1
Plastic Waste Management dropdown done ✓ | pages_visited=2
CRAWL_FINISHED: 8 pages
ALL DONE — pages complete
✅ EPR PLASTIC complete
```

**❌ Bad (crawler failed):**
```
❌ EPR PLASTIC failed: [TimeoutError] Page.goto timeout
```

---

## Step 4: Test Locally Before Committing

Before pushing to GitHub, test the crawler locally:

```bash
# Test single portal
python scripts/test_crawler.py "EPR PLASTIC"

# Test all portals
python scripts/test_crawler.py
```

If it works locally but fails in GitHub Actions, the issue is likely:
- Environment variables not set
- Cloudinary credentials missing
- Network differences (GitHub Actions can be blocked by some sites)

---

## Step 5: Manual Trigger Test

1. Go to **Actions** → **"Scheduled Crawler"**
2. Click **"Run workflow"** → **"Run workflow"**
3. Watch the logs in real-time

This helps you see errors immediately without waiting for 4:30 PM.

---

## Step 6: Fix Common Portal-Specific Issues

Edit `config.json` and add these options per portal:

```json
{
  "name": "EPR PLASTIC",
  "url": "https://eprplastic.cpcb.gov.in/#/plastic/home",
  "auth": "none",
  "crawl": {
    "only_home": true,
    "max_pages": 11,
    "timeout": 30000,
    "wait_for_network": true
  }
}
```

Key settings:
- `only_home: true` → Only crawl home page (faster, fewer errors)
- `max_pages: 11` → Stop after 11 pages (prevent infinite crawl)
- `timeout: 30000` → 30 second timeout per page (increase if needed)
- `wait_for_network: true` → Wait for network idle before capturing

---

## Step 7: Check Supabase Connection

If crawlers run but don't save to database:

```bash
# Test connection from your machine
psql -h aws-1-ap-northeast-1.pooler.supabase.com \
     -p 6543 \
     -U postgres.cvxhmlzesrwcrknpltpo \
     -d postgres \
     -c "SELECT 1;"
```

If it fails, Supabase credentials in GitHub might be wrong.

---

## Next Steps to Debug Your Issue

1. **Check GitHub Actions logs** (Steps 1-3 above)
2. **Paste the error message** from the logs
3. **Test locally** with `python scripts/test_crawler.py`
4. **Tell me which portal fails** and what the error is

Then I can help you fix it specifically!
