import sqlite3, os, json

DB = os.path.join(os.path.dirname(__file__), "..", "changes.db")

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    target_id = 142
    cur.execute("SELECT diff_detail FROM changes WHERE id=?", (target_id,))
    row = cur.fetchone()
    if not row:
        print("change id not found:", target_id)
        return
    detail = row[0]
    try:
        data = json.loads(detail)
    except Exception as e:
        print("cannot parse diff_detail:", e)
        return

    added = data.get("added_texts") or []
    removed = data.get("removed_texts") or []
    new_summary = None
    # heuristic: if any removed item mentions 'test' -> 'Test button removed'
    if any("test" in (t or "").lower() for t in removed):
        new_summary = "Test button removed (present in baseline, not in latest)"
    elif any("test" in (t or "").lower() for t in added):
        new_summary = "Test button added (new in latest snapshot)"
    else:
        new_summary = data.get("summary", "Page changed")

    data["summary"] = new_summary
    new_json = json.dumps(data)
    cur.execute("UPDATE changes SET diff_detail=? WHERE id=?", (new_json, target_id))
    conn.commit()
    print("Updated change id %s summary to: %s" % (target_id, new_summary))
    conn.close()

if __name__ == "__main__":
    main()

