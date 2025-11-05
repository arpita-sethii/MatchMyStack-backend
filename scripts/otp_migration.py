import sqlite3
from pathlib import Path

# Path to your database
DB_PATH = Path(__file__).parent.parent / "app.db"

def migrate_database():
    """Add OTP tables including pre-signup verification"""
    
    print(f"📂 Looking for database at: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("   Please update DB_PATH in this script to point to your app.db file")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔍 Checking current database schema...")
        
        # 1. Check if email_verified column exists
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
        
        # 2. Check if email_verifications table exists (for existing users)
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
        
        # 3. Check if presignup_verifications table exists (NEW for Option 1)
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='presignup_verifications'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating presignup_verifications table...")
            cursor.execute("""
                CREATE TABLE presignup_verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR NOT NULL,
                    otp_hash VARCHAR NOT NULL,
                    expires_at DATETIME NOT NULL,
                    consumed BOOLEAN DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    verified_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add index on email for faster lookups
            cursor.execute("""
                CREATE INDEX idx_presignup_email 
                ON presignup_verifications(email)
            """)
            
            print("✅ presignup_verifications table created")
        else:
            print("✓ presignup_verifications table already exists")
        
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
        
        print("\n📊 Users table schema:")
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
    print("🚀 Starting database migration (Option 1: Pre-signup OTP)...\n")
    migrate_database()