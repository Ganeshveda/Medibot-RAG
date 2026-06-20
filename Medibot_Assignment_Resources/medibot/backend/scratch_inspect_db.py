"""Quick script to inspect the mediassist.db schema and sample data."""
import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent.parent / "mediassist_data" / "mediassist_data" / "db" / "mediassist.db"
print(f"DB path: {db_path}")
print(f"Exists: {db_path.exists()}")

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# List tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f"\nTables: {[t[0] for t in tables]}")

for table_name in [t[0] for t in tables]:
    print(f"\n{'='*60}")
    print(f"TABLE: {table_name}")
    print('='*60)
    
    # Schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    print("\nColumns:")
    for col in columns:
        print(f"  {col[1]:25s} {col[2]:15s} {'NOT NULL' if col[3] else 'NULLABLE':10s} {'PK' if col[5] else ''}")
    
    # Row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"\nRow count: {count}")
    
    # Sample rows
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
    rows = cursor.fetchall()
    col_names = [col[1] for col in columns]
    print(f"\nSample rows:")
    print(f"  {col_names}")
    for row in rows:
        print(f"  {list(row)}")

conn.close()
