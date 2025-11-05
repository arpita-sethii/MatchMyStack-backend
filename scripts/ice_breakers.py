# backend/scripts/ice_breakers.py
import sys
from pathlib import Path

# ✅ FIX: Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

print(f"📂 Backend directory: {backend_dir}")
print(f"📂 Python path: {sys.path[0]}\n")

from app.db.session import SessionLocal
from app.models.models import Icebreaker

def seed_icebreakers():
    db = SessionLocal()
    
    # Check if icebreakers already exist
    existing = db.query(Icebreaker).count()
    print(f"Current icebreakers in database: {existing}")
    
    if existing > 0:
        print(f"\n⚠️  Database already has {existing} icebreakers.")
        response = input("Do you want to add more? (y/n): ")
        if response.lower() != 'y':
            print("❌ Cancelled.")
            db.close()
            return
    
    # Default icebreakers
    icebreakers = [
        ("project", "What's the most challenging part of this project?"),
        ("skills", "What technologies are you most excited to work with?"),
        ("availability", "How many hours per week can you commit?"),
        ("technical", "What's your experience with the required tech stack?"),
        ("team", "Do you prefer working solo or in a team?"),
        ("general", "What excites you most about this project?"),
        ("goals", "What are you hoping to learn from this?"),
        ("collaboration", "How do you prefer to communicate?"),
        ("timeline", "What's your ideal project timeline?"),
        ("experience", "Tell me about a similar project you've worked on"),
    ]
    
    print(f"\n➕ Adding {len(icebreakers)} icebreakers...")
    
    for category, text in icebreakers:
        ib = Icebreaker(
            category=category,
            template_text=text,
            is_active=True,
            usage_count=0
        )
        db.add(ib)
    
    db.commit()
    
    # Verify
    count = db.query(Icebreaker).count()
    print(f"✅ Successfully added icebreakers! Total now: {count}\n")
    
    # Show them
    print("📋 All icebreakers in database:")
    print("-" * 60)
    all_icebreakers = db.query(Icebreaker).all()
    for ib in all_icebreakers:
        status = "✓" if ib.is_active else "✗"
        print(f"  {status} {ib.id}. [{ib.category}] {ib.template_text}")
    print("-" * 60)
    
    db.close()

if __name__ == "__main__":
    print("🚀 Icebreaker Seeder\n")
    try:
        seed_icebreakers()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()