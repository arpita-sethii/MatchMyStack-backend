# backend/app/services/password_reset_service.py
import secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import User, PasswordReset
from app.services.email_service import EmailService
from app.core import config
import logging

logger = logging.getLogger(__name__)
email_service = EmailService()


def generate_reset_token() -> str:
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)


def create_password_reset_token(db: Session, user: User) -> str:
    """
    Create a password reset token for the given user.
    Invalidates any existing unused tokens for this user.
    Returns the reset token.
    """
    # Invalidate any existing unused tokens
    db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id,
        PasswordReset.used == False
    ).update({"used": True})
    db.commit()
    
    # Generate new token
    token = generate_reset_token()
    expires_at = datetime.utcnow() + timedelta(hours=1)  # Token valid for 1 hour
    
    # Create reset record
    reset = PasswordReset(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
        used=False
    )
    db.add(reset)
    db.commit()
    
    logger.info(f"Created password reset token for user {user.email}")
    return token


def send_password_reset_email(user_email: str, reset_token: str, frontend_url: str = None) -> bool:
    """
    Send password reset email with the reset link.
    
    Args:
        user_email: Email address to send the reset link to
        reset_token: The reset token
        frontend_url: Base URL of frontend (e.g., http://localhost:8080)
    """
    # Use frontend URL from env or default to localhost
    if not frontend_url:
        frontend_url = "http://localhost:8080"  # Default for dev
    
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"
    
    subject = "Reset Your MatchMyStack Password"
    body = f"""
Hello,

We received a request to reset your password for your MatchMyStack account.

Click the link below to reset your password:

{reset_link}

This link will expire in 1 hour.

If you didn't request a password reset, please ignore this email. Your password will remain unchanged.

Best regards,
MatchMyStack Team
"""
    
    try:
        success = email_service.send_email(user_email, subject, body)
        if success:
            logger.info(f"Password reset email sent to {user_email}")
        return success
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user_email}: {e}")
        return False


def validate_reset_token(db: Session, token: str) -> tuple[bool, str, PasswordReset | None]:
    """
    Validate a password reset token.
    
    Returns:
        (is_valid, message, reset_record)
    """
    # Find the reset record
    reset = db.query(PasswordReset).filter(
        PasswordReset.token == token
    ).first()
    
    if not reset:
        return False, "Invalid reset token", None
    
    # Check if already used
    if reset.used:
        return False, "This reset link has already been used", None
    
    # Check if expired
    if datetime.utcnow() > reset.expires_at:
        reset.used = True  # Mark as used to prevent reuse
        db.commit()
        return False, "This reset link has expired. Please request a new one", None
    
    return True, "Token is valid", reset


def reset_password_with_token(db: Session, token: str, new_password_hash: str) -> tuple[bool, str]:
    """
    Reset user's password using a valid token.
    
    Args:
        db: Database session
        token: Reset token
        new_password_hash: Already hashed new password
    
    Returns:
        (success, message)
    """
    # Validate token
    is_valid, message, reset = validate_reset_token(db, token)
    
    if not is_valid:
        return False, message
    
    # Get the user
    user = db.query(User).filter(User.id == reset.user_id).first()
    if not user:
        return False, "User not found"
    
    # Update password
    user.hashed_password = new_password_hash
    
    # Mark token as used
    reset.used = True
    
    # Commit changes
    db.add(user)
    db.add(reset)
    db.commit()
    
    logger.info(f"Password reset successful for user {user.email}")
    return True, "Password has been reset successfully"


def cleanup_expired_tokens(db: Session) -> int:
    """
    Clean up expired password reset tokens (optional maintenance task).
    Returns number of tokens deleted.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)  # Delete tokens older than 7 days
    
    count = db.query(PasswordReset).filter(
        PasswordReset.created_at < cutoff
    ).delete()
    
    db.commit()
    logger.info(f"Cleaned up {count} expired password reset tokens")
    return count