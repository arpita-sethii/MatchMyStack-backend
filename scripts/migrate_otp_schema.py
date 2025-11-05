import sqlite3
from pathlib import Path

# Path to your database
DB_PATH = Path(__file__).parent.parent / "app.db"

def migrate_database():
    """Add OTP-related columns and tables to existing database"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔍 Checking current database schema...")
        
        # Check if email_verified column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'email_verified' not in columns:
            print("➕ Adding email_verified column to users table...")
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0
            """)
            print("✅ email_verified column added")
        else:
            print("✓ email_verified column already exists")
        
        # Check if email_verifications table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='email_verifications'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating email_verifications table...")
            cursor.execute("""
                CREATE TABLE email_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    otp_hash VARCHAR NOT NULL,
                    expires_at DATETIME NOT NULL,
                    consumed BOOLEAN DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            print("✅ email_verifications table created")
        else:
            print("✓ email_verifications table already exists")
        
        # Commit changes
        conn.commit()
        print("\n🎉 Migration completed successfully!")
        
        # Verify the changes
        print("\n📊 Current users table schema:")
        cursor.execute("PRAGMA table_info(users)")
        for col in cursor.fetchall():
            print(f"  - {col[1]} ({col[2]})")
        
    except sqlite3.Error as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Starting database migration...\n")
    migrate_database()