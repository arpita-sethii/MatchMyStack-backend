# backend/scripts/create_matches_table.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import engine
from app.models.models import Base, Match

def create_matches_table():
    print("Creating matches table...")
    try:
        # Create only the Match table
        Base.metadata.create_all(bind=engine, tables=[Match.__table__])
        print("✅ Matches table created successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    create_matches_table()