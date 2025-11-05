import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Path to your database
DB_PATH = Path(__file__).parent.parent / "app.db"

def migrate_database():
    """Add chat system tables"""
    
    print(f"📂 Looking for database at: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("   Please update DB_PATH in this script to point to your app.db file")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔍 Checking current database schema...")
        
        # 1. Create chat_rooms table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='chat_rooms'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating chat_rooms table...")
            cursor.execute("""
                CREATE TABLE chat_rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    match_id INTEGER,
                    last_message_at DATETIME,
                    last_message_preview VARCHAR(200),
                    unread_count_user INTEGER DEFAULT 0,
                    unread_count_owner INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(match_id) REFERENCES matches(id)
                )
            """)
            
            # Index for fast lookups
            cursor.execute("""
                CREATE INDEX idx_chat_rooms_user_project 
                ON chat_rooms(user_id, project_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_chat_rooms_user 
                ON chat_rooms(user_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_chat_rooms_project 
                ON chat_rooms(project_id)
            """)
            
            print("✅ chat_rooms table created")
        else:
            print("✓ chat_rooms table already exists")
        
        # 2. Create messages table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='messages'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating messages table...")
            cursor.execute("""
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    message_type VARCHAR DEFAULT 'text',
                    content TEXT NOT NULL,
                    file_url VARCHAR,
                    file_name VARCHAR,
                    file_size INTEGER,
                    is_read BOOLEAN DEFAULT 0,
                    read_at DATETIME,
                    edited BOOLEAN DEFAULT 0,
                    deleted BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME,
                    FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
                    FOREIGN KEY(sender_id) REFERENCES users(id)
                )
            """)
            
            # Indexes for performance
            cursor.execute("""
                CREATE INDEX idx_messages_room 
                ON messages(room_id, created_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX idx_messages_sender 
                ON messages(sender_id)
            """)
            
            print("✅ messages table created")
        else:
            print("✓ messages table already exists")
        
        # 3. Create icebreakers table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='icebreakers'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating icebreakers table...")
            cursor.execute("""
                CREATE TABLE icebreakers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category VARCHAR NOT NULL,
                    template_text VARCHAR NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    usage_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Seed with default icebreakers
            icebreakers = [
                ("project", "What's a recent project you're proud of?"),
                ("skills", "What role do you want to play in this project?"),
                ("availability", "When are you available to start?"),
                ("technical", "Any stack preferences or hard constraints?"),
                ("team", "What's your ideal team size?"),
                ("general", "What excites you most about this project?"),
                ("experience", "What's your experience with the required tech stack?"),
                ("collaboration", "How do you prefer to collaborate (async, sync, hybrid)?"),
                ("goals", "What are you hoping to learn from this project?"),
                ("timeline", "What's your preferred project timeline?"),
            ]
            
            cursor.executemany("""
                INSERT INTO icebreakers (category, template_text, is_active, usage_count)
                VALUES (?, ?, 1, 0)
            """, icebreakers)
            
            print(f"✅ icebreakers table created with {len(icebreakers)} default icebreakers")
        else:
            print("✓ icebreakers table already exists")
        
        # 4. Create typing_indicators table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='typing_indicators'
        """)
        
        if not cursor.fetchone():
            print("➕ Creating typing_indicators table...")
            cursor.execute("""
                CREATE TABLE typing_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX idx_typing_room_user 
                ON typing_indicators(room_id, user_id)
            """)
            
            print("✅ typing_indicators table created")
        else:
            print("✓ typing_indicators table already exists")
        
        # Commit all changes
        conn.commit()
        print("\n🎉 Chat system migration completed successfully!")
        
        # Verify the changes
        print("\n📊 Current database tables:")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        for table in cursor.fetchall():
            print(f"  ✓ {table[0]}")
        
        print("\n📊 Chat-related table schemas:")
        for table in ['chat_rooms', 'messages', 'icebreakers', 'typing_indicators']:
            print(f"\n{table}:")
            cursor.execute(f"PRAGMA table_info({table})")
            for col in cursor.fetchall():
                print(f"  - {col[1]} ({col[2]})")
        
    except sqlite3.Error as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Starting chat system migration...\n")
    migrate_database()