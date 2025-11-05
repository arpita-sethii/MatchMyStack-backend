import smtplib
from email.message import EmailMessage
import logging
from typing import Optional
from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.smtp_user = SMTP_USER
        self.smtp_pass = SMTP_PASS
        self.email_from = EMAIL_FROM
        self.smtp_enabled = all([SMTP_HOST, SMTP_USER, SMTP_PASS])
    
    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """
        Send an email using SMTP. If SMTP not configured, log the message and return True (dev mode).
        """
        if not self.smtp_enabled:
            # Fallback for dev: just log the email (so OTP is visible in logs)
            logger.info("SMTP not configured — logging email instead of sending.")
            logger.info("Email to: %s\nSubject: %s\n\n%s", to_email, subject, body)
            return True

        try:
            msg = EmailMessage()
            msg["From"] = self.email_from
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(body)

            # Use TLS (STARTTLS) by default
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.smtp_user, self.smtp_pass)
                smtp.send_message(msg)

            logger.info("Sent email to %s via %s", to_email, self.smtp_host)
            return True
        except Exception as e:
            logger.exception("Failed to send email to %s: %s", to_email, e)
            return False
    
    def send_otp_email(self, to_email: str, otp_code: str) -> bool:
        """
        Send an OTP verification code via email.
        """
        subject = "Your MatchMyStack Verification Code"
        body = f"""
Hello,

Your verification code is: {otp_code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

Best regards,
MatchMyStack Team
"""
        return self.send_email(to_email, subject, body)


# Keep the old function for backward compatibility
def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Send an email using SMTP. If SMTP not configured, log the message and return True (dev mode).
    (Backward compatibility - use EmailService class instead)
    """
    service = EmailService()
    return service.send_email(to_email, subject, body)