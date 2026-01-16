"""
Inspect columns of Generated_Reports table.
Run: python -m backend.inspect_schema
"""
from backend.database import get_db_cursor

def main():
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'Generated_Reports'
            ORDER BY ordinal_position
            """
        )
        rows = cur.fetchall()
        print("Columns in Generated_Reports:")
        for name, dtype in rows:
            print(f" - {name}: {dtype}")

if __name__ == "__main__":
    main()
