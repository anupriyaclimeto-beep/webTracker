import requests
import json
import os

# Supabase connection details
SUPABASE_HOST = os.getenv("SUPABASE_HOST", "").replace("db.", "").replace(".postgres.supabase.co", "")
SUPABASE_URL = f"https://{SUPABASE_HOST}.supabase.co" if SUPABASE_HOST else ""
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_API_KEY", "")

def query_supabase(table, select="*", where_clause=None, order_by=None):
    """Query Supabase using REST API (lightweight, no psycopg2 needed)"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase credentials not configured")
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    params = {"select": select}
    if where_clause:
        params.update(where_clause)
    if order_by:
        params["order"] = order_by
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Supabase query failed: {e}")

def execute_supabase(table, data=None, method="POST"):
    """Execute write operations on Supabase using REST API"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase credentials not configured")
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Supabase operation failed: {e}")
