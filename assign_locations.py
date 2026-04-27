import sqlite3
import random
import os

db_path = 'instance/database.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cabinets = ['Cabinet A', 'Cabinet B', 'Cabinet C']

try:
    print("Assigning random locations (Cabinet A, B, C) to chemicals...")
    cursor.execute("SELECT id FROM chemical")
    chemical_ids = [row[0] for row in cursor.fetchall()]
    
    for cid in chemical_ids:
        location = random.choice(cabinets)
        cursor.execute("UPDATE chemical SET location = ? WHERE id = ?", (location, cid))
    
    conn.commit()
    print(f"Successfully updated {len(chemical_ids)} chemicals.")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
