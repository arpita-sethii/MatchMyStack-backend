import sqlite3
import hashlib
from datetime import datetime
import json

class Database:
    def __init__(self, db_path="data/matchmystack.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
    
    def init_database(self):
        """Create all necessary tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                password_hash TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Resumes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                raw_text TEXT,
                parsed_data TEXT,
                embedding TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Matches table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id_a INTEGER,
                user_id_b INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id_a) REFERENCES users(id),
                FOREIGN KEY (user_id_b) REFERENCES users(id),
                UNIQUE(user_id_a, user_id_b)
            )
        """)
        
        # Swipes table (track left/right swipes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS swipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swiper_id INTEGER,
                swiped_id INTEGER,
                direction TEXT,
                swiped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (swiper_id) REFERENCES users(id),
                FOREIGN KEY (swiped_id) REFERENCES users(id),
                UNIQUE(swiper_id, swiped_id)
            )
        """)
        
        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                sender_id INTEGER,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read BOOLEAN DEFAULT 0,
                FOREIGN KEY (match_id) REFERENCES matches(id),
                FOREIGN KEY (sender_id) REFERENCES users(id)
            )
        """)
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully!")
    
    # ==================== USER METHODS ====================
    
    def hash_password(self, password):
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, email, password, phone=None, name=None):
        """Create a new user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = self.hash_password(password)
        
        try:
            cursor.execute("""
                INSERT INTO users (email, password_hash, phone, name)
                VALUES (?, ?, ?, ?)
            """, (email, password_hash, phone, name))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return {"success": True, "user_id": user_id}
        except sqlite3.IntegrityError:
            conn.close()
            return {"success": False, "error": "Email already exists"}
    
    def verify_login(self, email, password):
        """Verify user login credentials"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = self.hash_password(password)
        
        cursor.execute("""
            SELECT id, email, name FROM users 
            WHERE email = ? AND password_hash = ?
        """, (email, password_hash))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {"success": True, "user": dict(user)}
        return {"success": False, "error": "Invalid credentials"}
    
    def get_user(self, user_id):
        """Get user by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        return dict(user) if user else None
    
    # ==================== RESUME METHODS ====================
    
    def save_resume(self, user_id, raw_text, parsed_data, embedding):
        """Save resume data for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO resumes (user_id, raw_text, parsed_data, embedding)
            VALUES (?, ?, ?, ?)
        """, (user_id, raw_text, json.dumps(parsed_data), json.dumps(embedding)))
        
        conn.commit()
        conn.close()
        return True
    
    def get_resume(self, user_id):
        """Get resume data for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM resumes WHERE user_id = ?", (user_id,))
        resume = cursor.fetchone()
        conn.close()
        
        if resume:
            resume_dict = dict(resume)
            resume_dict['parsed_data'] = json.loads(resume_dict['parsed_data'])
            resume_dict['embedding'] = json.loads(resume_dict['embedding'])
            return resume_dict
        return None
    
    def get_all_user_embeddings(self, exclude_user_id=None):
        """Get all user embeddings for matching"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if exclude_user_id:
            cursor.execute("""
                SELECT user_id, embedding, parsed_data FROM resumes 
                WHERE user_id != ?
            """, (exclude_user_id,))
        else:
            cursor.execute("SELECT user_id, embedding, parsed_data FROM resumes")
        
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            results.append({
                'user_id': row['user_id'],
                'embedding': json.loads(row['embedding']),
                'parsed_data': json.loads(row['parsed_data'])
            })
        return results
    
    # ==================== SWIPE METHODS ====================
    
    def save_swipe(self, swiper_id, swiped_id, direction):
        """Save a swipe (left/right)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO swipes (swiper_id, swiped_id, direction)
                VALUES (?, ?, ?)
            """, (swiper_id, swiped_id, direction))
            conn.commit()
            
            # Check if it's a mutual right swipe
            if direction == "right":
                cursor.execute("""
                    SELECT * FROM swipes 
                    WHERE swiper_id = ? AND swiped_id = ? AND direction = 'right'
                """, (swiped_id, swiper_id))
                
                mutual = cursor.fetchone()
                
                if mutual:
                    # Create a match!
                    self.create_match(swiper_id, swiped_id)
                    conn.close()
                    return {"success": True, "match": True}
            
            conn.close()
            return {"success": True, "match": False}
        except sqlite3.IntegrityError:
            conn.close()
            return {"success": False, "error": "Already swiped on this user"}
    
    def get_swiped_users(self, user_id):
        """Get all users that this user has already swiped on"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT swiped_id FROM swipes WHERE swiper_id = ?
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [row['swiped_id'] for row in rows]
    
    # ==================== MATCH METHODS ====================
    
    def create_match(self, user_id_a, user_id_b):
        """Create a match between two users"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Ensure consistent ordering
        if user_id_a > user_id_b:
            user_id_a, user_id_b = user_id_b, user_id_a
        
        try:
            cursor.execute("""
                INSERT INTO matches (user_id_a, user_id_b, status)
                VALUES (?, ?, 'active')
            """, (user_id_a, user_id_b))
            conn.commit()
            match_id = cursor.lastrowid
            conn.close()
            return match_id
        except sqlite3.IntegrityError:
            conn.close()
            return None
    
    def get_user_matches(self, user_id):
        """Get all matches for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT m.*, 
                   CASE 
                       WHEN m.user_id_a = ? THEN m.user_id_b 
                       ELSE m.user_id_a 
                   END as matched_user_id
            FROM matches m
            WHERE (m.user_id_a = ? OR m.user_id_b = ?) AND m.status = 'active'
        """, (user_id, user_id, user_id))
        
        matches = cursor.fetchall()
        conn.close()
        
        return [dict(match) for match in matches]
    
    # ==================== MESSAGE METHODS ====================
    
    def save_message(self, match_id, sender_id, content):
        """Save a chat message"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO messages (match_id, sender_id, content)
            VALUES (?, ?, ?)
        """, (match_id, sender_id, content))
        
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        
        return message_id
    
    def get_messages(self, match_id, limit=50):
        """Get messages for a match"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM messages 
            WHERE match_id = ? 
            ORDER BY timestamp ASC 
            LIMIT ?
        """, (match_id, limit))
        
        messages = cursor.fetchall()
        conn.close()
        
        return [dict(msg) for msg in messages]
    
    def mark_messages_read(self, match_id, user_id):
        """Mark messages as read"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE messages 
            SET read = 1 
            WHERE match_id = ? AND sender_id != ? AND read = 0
        """, (match_id, user_id))
        
        conn.commit()
        conn.close()


# Initialize database when module is imported
if __name__ == "__main__":
    db = Database()
    print("Database setup complete!")