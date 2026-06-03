import storage, json, sys

def list_columns():
    conn = storage.get_conn()
    cur = conn.cursor()
    # Query information_schema for column names and types
    query = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s AND table_schema = %s
        ORDER BY ordinal_position
    """
    cur.execute(query, ('changes', 'public'))
    rows = cur.fetchall()
    for col, dtype in rows:
        print(f"{col}\t{dtype}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    list_columns()
