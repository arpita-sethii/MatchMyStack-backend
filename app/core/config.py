import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env (make sure .env exists at project root)
load_dotenv()

# --- BASE & DATABASE ---
BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'app.db'}")

# --- JWT CONFIGURATION ---
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-change-me")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24))  # default: 1 day

# --- SMTP / EMAIL CONFIGURATION ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))  # 465 for SSL, 587 for STARTTLS
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "no-reply@example.com")

# Derived flag to detect if SMTP is configured
SMTP_ENABLED = all([SMTP_HOST, SMTP_USER, SMTP_PASS])

# --- OTP CONFIGURATION ---
OTP_LENGTH = int(os.getenv("OTP_LENGTH", 6))
OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", 10))
OTP_MAX_RESEND_ATTEMPTS = int(os.getenv("OTP_MAX_RESEND_ATTEMPTS", 5))

# --- Debug info (optional, remove in production) ---
if not SMTP_ENABLED:
    print(
        "\n⚠️  [WARNING] SMTP credentials not configured. "
        "OTP emails will be logged to console instead of being sent.\n"
    )
else:
    print(f"\n✅ SMTP enabled. Emails will be sent via {SMTP_HOST}:{SMTP_PORT} as {SMTP_USER}\n")
