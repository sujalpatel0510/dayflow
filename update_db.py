from app import app, db
from sqlalchemy import text

def update_database():
    with app.app_context():
        print("Updating database schema...")

        # 1. Create the 'leaves' table if it doesn't exist
        db.create_all()
        print("✅ Checked/Created tables (users, leaves)")

        # 2. Add columns to 'leaves' if they were missing (for existing tables)
        with db.engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")

            # List of columns to check/add for 'leaves' table
            new_columns = [
                ("approved_by", "INTEGER"),
                ("number_of_days", "INTEGER"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            ]

            for col_name, col_type in new_columns:
                try:
                    conn.execute(text(f"ALTER TABLE leaves ADD COLUMN {col_name} {col_type}"))
                    print(f"✅ Added column '{col_name}' to leaves")
                except Exception:
                    pass # Column likely already exists, ignore error

if __name__ == "__main__":
    update_database()