import sqlite3
import os

db_path = 'instance/database.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("Performing advanced migration for usage_log...")
    
    # 1. Check current columns
    cursor.execute("PRAGMA table_info(usage_log)")
    cols = {col[1]: col for col in cursor.fetchall()}
    
    # 2. Rename old table
    cursor.execute("ALTER TABLE usage_log RENAME TO usage_log_old")
    
    # 3. Create new table with correct schema (no quantity_used, has action and quantity_change)
    cursor.execute("""
        CREATE TABLE usage_log (
            id INTEGER PRIMARY KEY,
            chemical_id INTEGER NOT NULL,
            user_name VARCHAR(100) NOT NULL,
            action VARCHAR(50) NOT NULL DEFAULT 'Usage',
            quantity_change FLOAT NOT NULL,
            purpose VARCHAR(255),
            date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chemical_id) REFERENCES chemical(id)
        )
    """)
    
    # 4. Copy data
    if 'quantity_used' in cols:
        print("Migrating data from quantity_used to quantity_change...")
        cursor.execute("""
            INSERT INTO usage_log (id, chemical_id, user_name, action, quantity_change, purpose, date)
            SELECT id, chemical_id, user_name, 'Usage', -quantity_used, purpose, date
            FROM usage_log_old
        """)
    elif 'quantity_change' in cols:
        print("Copying existing quantity_change data...")
        cursor.execute("""
            INSERT INTO usage_log (id, chemical_id, user_name, action, quantity_change, purpose, date)
            SELECT id, chemical_id, user_name, action, quantity_change, purpose, date
            FROM usage_log_old
        """)
    
    # 5. Drop old table
    cursor.execute("DROP TABLE usage_log_old")
    
    conn.commit()
    print("Advanced migration successful!")
except Exception as e:
    print(f"Error during migration: {e}")
    conn.rollback()
finally:
    conn.close()
