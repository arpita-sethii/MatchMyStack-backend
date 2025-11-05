import sqlite3
from pathlib import Path

# Path to your database
DB_PATH = Path(__file__).parent.parent / "app.db"

def migrate_database():
    """Add password_resets table for forgot password feature"""
    
    print(f"📂 Looking for database at: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("   Please update DB_PATH in this script to point to your app.db file")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔍 Checking current database schema...")
        
        # Check if password_resets table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='password_resets'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating password_resets table...")
            cursor.execute("""
                CREATE TABLE password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token VARCHAR UNIQUE NOT NULL,
                    expires_at DATETIME NOT NULL,
                    used BOOLEAN DEFAULT 0 NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
            # Add index on token for faster lookups
            cursor.execute("""
                CREATE INDEX idx_password_reset_token 
                ON password_resets(token)
            """)
            
            # Add index on user_id for faster lookups
            cursor.execute("""
                CREATE INDEX idx_password_reset_user_id 
                ON password_resets(user_id)
            """)
            
            print("✅ password_resets table created with indexes")
        else:
            print("✓ password_resets table already exists")
        
        # Commit changes
        conn.commit()
        print("\n🎉 Migration completed successfully!")
        
        # Verify the changes
        print("\n📊 Current database tables:")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        for table in cursor.fetchall():
            print(f"  ✓ {table[0]}")
        
        print("\n📊 Password resets table schema:")
        cursor.execute("PRAGMA table_info(password_resets)")
        for col in cursor.fetchall():
            print(f"  - {col[1]} ({col[2]})")
        
    except sqlite3.Error as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Starting password reset table migration...\n")
    migrate_database()