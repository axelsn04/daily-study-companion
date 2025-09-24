import os
import yagmail
from dotenv import load_dotenv

load_dotenv()

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")

def send_email(subject: str, html_path: str):
    # Requiere que tengas sesión con keychain o .yagmail con credenciales,
    # o que exportes la variable de entorno YAGMAIL_PASSWORD (App Password).
    yag = yagmail.SMTP(EMAIL_FROM)
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    yag.send(to=EMAIL_TO, subject=subject, contents=[html])
