# backend/app/api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.models import User
from app.schemas.schemas import (
    UserCreate,
    UserOut,
    Token,
    OTPVerifyRequest,
    ResendOTPRequest,
    OTPResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PasswordResetResponse,
)
from app.core.security import hash_password, verify_password, create_access_token
from app.services.otp_service import create_and_send_otp, verify_otp, create_presignup_otp, verify_presignup_otp
from app.services.password_reset_service import (
    create_password_reset_token,
    send_password_reset_email,
    reset_password_with_token,
)
import logging
from typing import Dict

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/signup", response_model=UserOut)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user. 
    Note: For OTP-first flow, users should verify OTP before calling this.
    """
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=user_in.email,
        name=user_in.name,
        hashed_password=hash_password(user_in.password),
        email_verified=False,  # Will be set to True if OTP was verified first
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login", response_model=Token)
def login(
    username: str = Form(...),  # OAuth2 expects 'username' field
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Login (form-encoded) — returns JWT access token on success.
    """
    user = db.query(User).filter(User.email == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return {"access_token": token, "token_type": "bearer"}


# ----------------- OTP Endpoints (Pre-Signup Flow) ----------------- #

@router.post("/request_otp", response_model=OTPResponse)
def request_otp_underscore(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    """
    Request OTP for email verification BEFORE signup.
    This allows users to verify their email before creating an account.
    """
    # Check if user already exists
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        # User already exists - use regular OTP flow
        try:
            create_and_send_otp(db, existing)
            return OTPResponse(success=True, message="OTP sent successfully")
        except Exception as e:
            logger.exception("Failed to send OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to send OTP")
    else:
        # User doesn't exist yet - create pre-signup OTP
        try:
            create_presignup_otp(db, payload.email)
            return OTPResponse(success=True, message="Verification code sent to your email")
        except Exception as e:
            logger.exception("Failed to send pre-signup OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to send verification code")


@router.post("/request-otp", response_model=OTPResponse)
def request_otp_dash(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    """
    Request OTP for email verification BEFORE signup (kebab-case version).
    """
    # Check if user already exists
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        # User already exists - use regular OTP flow
        try:
            create_and_send_otp(db, existing)
            return OTPResponse(success=True, message="OTP sent successfully")
        except Exception as e:
            logger.exception("Failed to send OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to send OTP")
    else:
        # User doesn't exist yet - create pre-signup OTP
        try:
            create_presignup_otp(db, payload.email)
            return OTPResponse(success=True, message="Verification code sent to your email")
        except Exception as e:
            logger.exception("Failed to send pre-signup OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to send verification code")


@router.post("/verify_otp", response_model=OTPResponse)
def verify_otp_underscore(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify OTP code.
    Works for both pre-signup OTP and post-signup email verification.
    """
    # Check if user exists
    user = db.query(User).filter(User.email == payload.email).first()
    
    if user:
        # User exists - verify and mark email as verified
        try:
            ok, message = verify_otp(db, payload.email, payload.otp)
            if not ok:
                raise HTTPException(status_code=400, detail=message)

            # Mark email as verified
            if not user.email_verified:
                user.email_verified = True
                db.add(user)
                db.commit()

            return OTPResponse(success=True, message="Email verified successfully")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error verifying OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to verify OTP")
    else:
        # User doesn't exist yet - verify pre-signup OTP
        try:
            ok, message = verify_presignup_otp(db, payload.email, payload.otp)
            if not ok:
                raise HTTPException(status_code=400, detail=message)
            
            return OTPResponse(success=True, message="Email verified! You can now create your account.")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error verifying pre-signup OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to verify code")


@router.post("/verify-otp", response_model=OTPResponse)
def verify_otp_dash(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify OTP code (kebab-case version).
    Works for both pre-signup OTP and post-signup email verification.
    """
    # Check if user exists
    user = db.query(User).filter(User.email == payload.email).first()
    
    if user:
        # User exists - verify and mark email as verified
        try:
            ok, message = verify_otp(db, payload.email, payload.otp)
            if not ok:
                raise HTTPException(status_code=400, detail=message)

            # Mark email as verified
            if not user.email_verified:
                user.email_verified = True
                db.add(user)
                db.commit()

            return OTPResponse(success=True, message="Email verified successfully")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error verifying OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to verify OTP")
    else:
        # User doesn't exist yet - verify pre-signup OTP
        try:
            ok, message = verify_presignup_otp(db, payload.email, payload.otp)
            if not ok:
                raise HTTPException(status_code=400, detail=message)
            
            return OTPResponse(success=True, message="Email verified! You can now create your account.")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Error verifying pre-signup OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to verify code")


@router.post("/resend-otp", response_model=OTPResponse)
def resend_otp_endpoint(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    """
    Resend verification OTP.
    Works for both existing users and pre-signup verification.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    
    if user:
        # User exists - send regular OTP
        try:
            create_and_send_otp(db, user)
            return OTPResponse(success=True, message="Verification code resent")
        except Exception as e:
            logger.exception("Failed to resend OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to resend OTP")
    else:
        # User doesn't exist - send pre-signup OTP
        try:
            create_presignup_otp(db, payload.email)
            return OTPResponse(success=True, message="Verification code resent")
        except Exception as e:
            logger.exception("Failed to resend pre-signup OTP: %s", e)
            raise HTTPException(status_code=500, detail="Failed to resend verification code")


# ----------------- NEW: Password Reset Endpoints ----------------- #

@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request a password reset link.
    Sends an email with a reset token if the user exists.
    Always returns success (to prevent email enumeration).
    """
    try:
        # Find user
        user = db.query(User).filter(User.email == payload.email).first()
        
        if user:
            # Create reset token
            token = create_password_reset_token(db, user)
            
            # Send email with reset link
            # TODO: Get frontend URL from config or environment
            frontend_url = "http://localhost:5173"  # Default for dev
            send_password_reset_email(user.email, token, frontend_url)
            
            logger.info(f"Password reset requested for {payload.email}")
        else:
            # User doesn't exist, but don't reveal this to prevent email enumeration
            logger.info(f"Password reset requested for non-existent email: {payload.email}")
        
        # Always return success message
        return PasswordResetResponse(
            success=True,
            message="If an account exists with that email, a password reset link has been sent."
        )
    
    except Exception as e:
        logger.exception(f"Error in forgot_password: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process password reset request"
        )


@router.post("/reset-password", response_model=PasswordResetResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using the token from the email link.
    """
    try:
        # Hash the new password
        new_password_hash = hash_password(payload.new_password)
        
        # Reset password with token
        success, message = reset_password_with_token(db, payload.token, new_password_hash)
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return PasswordResetResponse(success=True, message=message)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in reset_password: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to reset password"
        )