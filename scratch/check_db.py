from app import app, db, DashboardConfig
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Tables: {tables}")
    if 'dashboard_config' in tables:
        print("dashboard_config table exists.")
    else:
        print("dashboard_config table MISSING. Creating all...")
        db.create_all()
        print("Done.")
