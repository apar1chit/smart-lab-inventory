import sqlite3
import os

db_path = 'instance/database.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("Checking usage_log table...")
    cursor.execute("PRAGMA table_info(usage_log)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'action' not in columns:
        print("Adding 'action' column...")
        cursor.execute("ALTER TABLE usage_log ADD COLUMN action VARCHAR(50) DEFAULT 'Usage'")
    
    if 'quantity_change' not in columns:
        print("Adding 'quantity_change' column...")
        cursor.execute("ALTER TABLE usage_log ADD COLUMN quantity_change FLOAT DEFAULT 0.0")
        
        # If quantity_used exists, migrate it to quantity_change (as negative)
        if 'quantity_used' in columns:
            print("Migrating quantity_used to quantity_change...")
            cursor.execute("UPDATE usage_log SET quantity_change = -quantity_used")
    
    conn.commit()
    print("Migration successful!")
except Exception as e:
    print(f"Error during migration: {e}")
    conn.rollback()
finally:
    conn.close()
