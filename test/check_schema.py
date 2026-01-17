"""Quick schema checker for troubleshooting."""
from backend.database import get_db_cursor
from psycopg2.extras import RealDictCursor

print("\n=== Checking Database Schema ===\n")

with get_db_cursor(RealDictCursor) as cur:
    # Check Companies table
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'Companies'
        ORDER BY ordinal_position
    """)
    companies_cols = cur.fetchall()
    print("Companies table columns:")
    if companies_cols:
        for row in companies_cols:
            print(f"  - {row['column_name']}: {row['data_type']}")
    else:
        print("  (Table not found or has no columns)")
    
    # Check Generated_Reports table
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'Generated_Reports'
        ORDER BY ordinal_position
    """)
    reports_cols = cur.fetchall()
    print("\nGenerated_Reports table columns:")
    if reports_cols:
        for row in reports_cols:
            print(f"  - {row['column_name']}: {row['data_type']}")
    else:
        print("  (Table not found or has no columns)")

print("\n=== Done ===\n")
