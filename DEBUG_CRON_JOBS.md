# Debugging: Cron Jobs Not Running

## Quick Checklist to Debug 🔍

### Step 1: Verify Workflow on GitHub
1. Go to your GitHub repo: **github.com/anupriyaclimeto-beep/webTracker**
2. Click **"Actions"** tab
3. Look for workflows:
   - `Scheduled Crawler Test (5:00 PM UTC)` 
   - `Scheduled Crawler (5:15 PM IST)`

**What to check:**
- ✅ Is there a green checkmark (success)?
- ❌ Is there a red X (failure)?
- ⏳ Is it still running (yellow)?
- ❓ Has it never run (no history)?

---

### Step 2: Common Issues

**Issue 1: Workflow Never Ran**
- GitHub cron jobs sometimes have a 5-15 minute delay
- Solution: Click "Run workflow" manually from the Actions tab to test immediately

**Issue 2: Workflow Failed**
- Check the logs by clicking on the failed run
- Look for errors like:
  - `SUPABASE_URL not found` → Environment variables not set
  - `Playwright timeout` → Portal taking too long
  - `Connection refused` → Database unreachable

**Issue 3: Workflow Passed But No Changes Shown**
- The crawler ran, but no new changes detected
- Check if portals actually changed since last run
- Or check if database update worked

---

### Step 3: Manual Test Right Now

Go to GitHub → Actions → "Scheduled Crawler Test (5:00 PM UTC)"
- Click **"Run workflow"** button
- Select branch: **main**
- Click **"Run workflow"**

This will run the crawler immediately and you can watch the logs in real-time.

---

### Step 4: Check Supabase Database

If workflow ran but data didn't update:

1. Go to **supabase.com** → Your project
2. Check tables:
   - `crawl_logs` → Latest entry should be today
   - `snapshots` → Should have new entries
   - `changes` → Should show new changes

---

### Step 5: Check Streamlit App Logs

On your Streamlit Cloud deployment:
1. Go to **streamlit.app** settings
2. Click "Manage app"
3. Check "Logs" for errors

---

## What I Recommend Right Now:

1. **Go to GitHub Actions** and manually trigger the workflow
2. **Watch the logs** as it runs (click on the job to see real-time output)
3. **Report any errors** you see
4. Then we can fix the issue

---

## Why Cron Jobs Might Not Have Run Yet:

1. ⏱️ **GitHub delay** - Cron jobs can be delayed 5-15 minutes
2. 🔐 **Secrets not set** - Environment variables missing
3. 🐛 **Workflow error** - Portal timeout or database connection issue
4. 📊 **No changes detected** - Site didn't change, so nothing new to show

---

## Next Step: You Should...

**Option A: Manual Test Right Now** (Fastest)
- Go to GitHub Actions
- Click the workflow name
- Click "Run workflow"
- Wait 2-3 minutes and refresh your Streamlit app

**Option B: Wait for Next Scheduled Run**
- Next run: 5:15 PM IST (in a few minutes)
- Check app around 5:30 PM IST

Which one would you like to do?
