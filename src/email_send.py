# src/email_send.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterable, Optional

import yagmail

EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[Daily Companion]")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
EMAIL_EMBED_MODE = (os.getenv("EMAIL_EMBED_MODE", "attachment") or "attachment").lower()
REPORT_PUBLIC_URL = os.getenv("REPORT_PUBLIC_URL", "").strip()


def _ensure_list(x: Optional[Iterable[str]]) -> list[str]:
    if not x:
        return []
    return list(x)


def send_email(subject: str, html_path: str, attachments: Optional[Iterable[str]] = None) -> None:
    """
    Sends an email.
    Mode:
      - attachment (recommended): send a simple body and attach the HTML (no CSS inlining).
      - inline: embed the HTML into the body (premailer inliner). Not recommended for modern CSS.
    """
    if not EMAIL_FROM or not EMAIL_TO or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Faltan credenciales de email (EMAIL_FROM, EMAIL_TO, GMAIL_APP_PASSWORD)")

    to_list = [t.strip() for t in EMAIL_TO.split(",") if t.strip()]

    html_text = Path(html_path).read_text(encoding="utf-8")
    full_subject = f"{SUBJECT_PREFIX} {subject}".strip()

    # Build body
    body_parts: list = []
    if EMAIL_EMBED_MODE == "inline":
        # This will try to inline CSS (may look broken with modern CSS)
        body_parts.append(yagmail.inline(html_text))
    else:
        # Clean, portable: simple body + attachment
        line_link = f'<p>Open the attached report, or view it online: <a href="{REPORT_PUBLIC_URL}">{REPORT_PUBLIC_URL}</a></p>' if REPORT_PUBLIC_URL else "<p>Open the attached report in your browser.</p>"
        summary = "<h3>Daily Study & News</h3>" + line_link
        body_parts.append(summary)

    # Attachments: include report + charts
    final_attachments = _ensure_list(attachments)
    # Always attach the HTML so it opens nicely in browser
    if html_path not in final_attachments:
        final_attachments.insert(0, html_path)

    yag = yagmail.SMTP(user=EMAIL_FROM, password=GMAIL_APP_PASSWORD)
    try:
        yag.send(
            to=to_list,
            subject=full_subject,
            contents=body_parts,
            attachments=final_attachments,
        )
        print(f"[email] Enviado a {', '.join(to_list)} (mode={EMAIL_EMBED_MODE})")
    finally:
        yag.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True, help="Ruta al reporte HTML para enviar")
    ap.add_argument("--subject", default="Daily report")
    ap.add_argument("--attach", nargs="*", default=[], help="Rutas extra a adjuntar")
    args = ap.parse_args()
    send_email(args.subject, args.html, args.attach)
