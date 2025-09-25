# src/email_send.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterable, Optional, List

import yagmail

EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[Daily Companion]")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
EMAIL_EMBED_MODE = (os.getenv("EMAIL_EMBED_MODE", "attachment") or "attachment").lower()
REPORT_PUBLIC_URL = (os.getenv("REPORT_PUBLIC_URL", "") or "").strip()


def _ensure_list(x: Optional[Iterable[str]]) -> List[str]:
    return list(x) if x else []


def send_email(
    subject: str,
    html_path: str,
    attachments: Optional[Iterable[str]] = None,
    extra_html: Optional[str] = None,   # <- NUEVO
) -> None:
    """
    Modes:
      - linkonly: si extra_html está presente -> se usa SOLO extra_html como body.
                  si NO hay extra_html -> se manda un body minimal con el link público.
      - attachment (default): body breve + adjunta HTML (y extras opcionales).
      - inline: pega el HTML completo como cuerpo (no recomendable por CSS moderno).
    """
    if not EMAIL_FROM or not EMAIL_TO or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Faltan credenciales de email (EMAIL_FROM, EMAIL_TO, GMAIL_APP_PASSWORD)")

    to_list = [t.strip() for t in EMAIL_TO.split(",") if t.strip()]
    full_subject = f"{SUBJECT_PREFIX} {subject}".strip()

    contents: List = []
    final_attachments: List[str] = []  # siempre definida
    mode = EMAIL_EMBED_MODE

    if mode == "linkonly":
        if extra_html:
            # SOLO el HTML extra que nos pasas (sin encabezado/link por defecto)
            contents.append(extra_html)
        else:
            # fallback minimal si no nos diste extra_html
            body = ["<h3>Daily Study & News</h3>"]
            if REPORT_PUBLIC_URL:
                body.append(f'<p>Abre tu reporte aquí: <a href="{REPORT_PUBLIC_URL}">{REPORT_PUBLIC_URL}</a></p>')
            contents.append("\n".join(body))
        # sin adjuntos en linkonly

    elif mode == "inline":
        html_text = Path(html_path).read_text(encoding="utf-8")
        body = html_text + (extra_html or "")
        contents.append(yagmail.inline(body))
        # sin adjuntos

    else:
        # attachment
        link = f' <a href="{REPORT_PUBLIC_URL}">{REPORT_PUBLIC_URL}</a>' if REPORT_PUBLIC_URL else ""
        body = (
            "<h3>Daily Study & News</h3><p>Adjuntamos tu reporte del día.</p>"
            + (f"<p>También online: {link}</p>" if link else "")
        )
        if extra_html:
            body += ("\n" + extra_html)
        contents.append(body)

        final_attachments = _ensure_list(attachments)
        if html_path not in final_attachments:
            final_attachments.insert(0, html_path)

    yag = yagmail.SMTP(user=EMAIL_FROM, password=GMAIL_APP_PASSWORD)
    try:
        yag.send(
            to=to_list,
            subject=full_subject,
            contents=contents,
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
