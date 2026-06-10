# Quick Steps to Manually Trigger & Debug Cron Job

## Step 1: Go to GitHub Actions
1. Open: https://github.com/anupriyaclimeto-beep/webTracker/actions
2. Click on **"Scheduled Crawler Test (5:00 PM UTC)"** in the left sidebar

## Step 2: Click "Run workflow"
1. Click the **"Run workflow"** button (top right, blue button)
2. Select branch: **main**
3. Click **"Run workflow"** again to confirm

## Step 3: Watch the Logs
1. A new run will appear in the history
2. Click on it to see real-time logs
3. Wait 2-3 minutes for it to complete

## Step 4: Check for Errors
Look for error messages like:
- `SyntaxError` - Code error
- `ModuleNotFoundError` - Missing package
- `Connection refused` - Database connection issue
- `Playwright timeout` - Portal taking too long
- `Exit code 1` - General failure

## Step 5: Refresh Streamlit App
After the run completes (check mark = success):
1. Go to your Streamlit app: https://webtracker-gsbsjdtxlbaz8vkahmdxss.streamlit.app/
2. Press F5 or refresh the page
3. Check if "Last crawl" time updated

---

## Please Try This Now & Tell Me:
1. ✅ Did you click "Run workflow"?
2. ✅ What is the status (green checkmark or red X)?
3. ✅ If red X, what error do you see in the logs?
4. ✅ Did the Streamlit app data update?

Once we fix this, the scheduled runs will work automatically! 🚀
