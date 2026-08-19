import resend
import random
import os

resend.api_key = os.getenv("RESEND_API_KEY")

def generate_otp() -> str:
    return str(random.randint(100000, 999999))

def send_otp_email(to_email: str, code: str):
    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": to_email,
        "subject": "Codul tau de verificare",
        "html": f"<p>Codul tau de verificare este: <strong>{code}</strong></p><p>Expira in 5 minute.</p>"
    })
