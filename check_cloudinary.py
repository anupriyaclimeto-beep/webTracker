import storage, json

def main():
    rows = storage.get_all_changes()
    if not rows:
        print("No rows found in Supabase.")
        return
    latest = rows[0]
    print("--- Latest record ---")
    print("Portal          :", latest.get("portal"))
    print("URL             :", latest.get("url"))
    print("Screenshot URL  :", latest.get("screenshot_url"))
    print("HTML URL        :", latest.get("html_url"))
    # Show a couple of older rows as well
    for i, row in enumerate(rows[1:6], start=1):
        print(f"[{i}] portal={row.get('portal')} screenshot_url={row.get('screenshot_url')}")

if __name__ == "__main__":
    main()
