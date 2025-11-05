# backend/app/services/otp_service.py
import secrets
import hashlib
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import User, EmailVerification, PreSignupVerification
from app.core import config  # Import the module, not settings object
from app.services.email_service import EmailService
import logging

logger = logging.getLogger(__name__)
email_service = EmailService()


def generate_otp_code(length: int = None) -> str:
    """Generate a random numeric OTP code"""
    if length is None:
        length = config.OTP_LENGTH
    return ''.join([str(secrets.randbelow(10)) for _ in range(length)])


def hash_otp(otp: str) -> str:
    """Hash OTP for secure storage"""
    return hashlib.sha256(otp.encode()).hexdigest()


# ============ EXISTING USER OTP (Post-Signup) ============

def create_and_send_otp(db: Session, user: User) -> None:
    """
    Create and send OTP for an existing user (post-signup verification)
    """
    # Generate OTP
    otp_code = generate_otp_code()
    otp_hash_value = hash_otp(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=config.OTP_EXPIRY_MINUTES)
    
    # Invalidate any existing OTPs for this user
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.consumed == False
    ).update({"consumed": True})
    
    # Create new OTP record
    verification = EmailVerification(
        user_id=user.id,
        otp_hash=otp_hash_value,
        expires_at=expires_at,
        consumed=False,
        attempts=0
    )
    db.add(verification)
    db.commit()
    
    # Send email
    try:
        email_service.send_otp_email(user.email, otp_code)
        logger.info(f"OTP sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send OTP email to {user.email}: {e}")
        raise


def verify_otp(db: Session, email: str, otp: str) -> tuple[bool, str]:
    """
    Verify OTP for an existing user
    Returns (success, message)
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False, "User not found"
    
    # Find the latest non-consumed OTP
    verification = db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.consumed == False
    ).order_by(EmailVerification.created_at.desc()).first()
    
    if not verification:
        return False, "No verification code found. Please request a new one."
    
    # Check expiry
    if datetime.utcnow() > verification.expires_at:
        verification.consumed = True
        db.commit()
        return False, "Verification code expired. Please request a new one."
    
    # Check OTP
    otp_hash_value = hash_otp(otp)
    if verification.otp_hash != otp_hash_value:
        verification.attempts += 1
        db.commit()
        
        if verification.attempts >= 3:
            verification.consumed = True
            db.commit()
            return False, "Too many incorrect attempts. Please request a new code."
        
        return False, "Invalid verification code"
    
    # Success - mark as consumed
    verification.consumed = True
    db.commit()
    
    return True, "Verification successful"


# ============ PRE-SIGNUP OTP (Before Account Creation) ============

def create_presignup_otp(db: Session, email: str) -> None:
    """
    Create and send OTP for email verification BEFORE signup.
    This doesn't require a user account to exist.
    """
    # Generate OTP
    otp_code = generate_otp_code()
    otp_hash_value = hash_otp(otp_code)
    expires_at = datetime.utcnow() + timedelta(minutes=config.OTP_EXPIRY_MINUTES)
    
    # Invalidate any existing pre-signup OTPs for this email
    db.query(PreSignupVerification).filter(
        PreSignupVerification.email == email,
        PreSignupVerification.consumed == False
    ).update({"consumed": True})
    db.commit()
    
    # Create new pre-signup verification record
    verification = PreSignupVerification(
        email=email,
        otp_hash=otp_hash_value,
        expires_at=expires_at,
        consumed=False,
        attempts=0
    )
    db.add(verification)
    db.commit()
    
    # Send email
    try:
        email_service.send_otp_email(email, otp_code)
        logger.info(f"Pre-signup OTP sent to {email}")
    except Exception as e:
        logger.error(f"Failed to send pre-signup OTP email to {email}: {e}")
        raise


def verify_presignup_otp(db: Session, email: str, otp: str) -> tuple[bool, str]:
    """
    Verify pre-signup OTP (before user account exists)
    Returns (success, message)
    """
    # Find the latest non-consumed pre-signup OTP
    verification = db.query(PreSignupVerification).filter(
        PreSignupVerification.email == email,
        PreSignupVerification.consumed == False
    ).order_by(PreSignupVerification.created_at.desc()).first()
    
    if not verification:
        return False, "No verification code found. Please request a new one."
    
    # Check expiry
    if datetime.utcnow() > verification.expires_at:
        verification.consumed = True
        db.commit()
        return False, "Verification code expired. Please request a new one."
    
    # Check OTP
    otp_hash_value = hash_otp(otp)
    if verification.otp_hash != otp_hash_value:
        verification.attempts += 1
        db.commit()
        
        if verification.attempts >= 3:
            verification.consumed = True
            db.commit()
            return False, "Too many incorrect attempts. Please request a new code."
        
        return False, "Invalid verification code"
    
    # Success - mark as consumed
    verification.consumed = True
    verification.verified_at = datetime.utcnow()
    db.commit()
    
    return True, "Email verified successfully"


def is_email_verified_presignup(db: Session, email: str) -> bool:
    """
    Check if an email was verified via pre-signup OTP flow
    (within the last 24 hours to prevent abuse)
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)
    
    verification = db.query(PreSignupVerification).filter(
        PreSignupVerification.email == email,
        PreSignupVerification.consumed == True,
        PreSignupVerification.verified_at.isnot(None),
        PreSignupVerification.verified_at > cutoff
    ).first()
    
    return verification is not None