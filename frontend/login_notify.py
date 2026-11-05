"""Aviso por correo cuando un usuario inicia sesión.

Es opcional: si faltan las variables de entorno no hace nada. Nunca bloquea ni
rompe el login: el envío corre en un hilo aparte y cualquier error solo se registra.

Variables de entorno:
  PREGRADER_NOTIFY_TO         destinatarios del aviso, separados por coma
  PREGRADER_SMTP_HOST         servidor SMTP (p. ej. smtp.gmail.com)
  PREGRADER_SMTP_PORT         puerto STARTTLS (por defecto 587)
  PREGRADER_SMTP_USER         usuario SMTP
  PREGRADER_SMTP_PASSWORD     contraseña SMTP (en Gmail, una contraseña de aplicación)
  PREGRADER_NOTIFY_FROM       remitente (por defecto, PREGRADER_SMTP_USER)
"""

import logging
import os
import re
import smtplib
import threading
from email.message import EmailMessage

log = logging.getLogger("pregrader.notify")


def _config():
    host = os.environ.get("PREGRADER_SMTP_HOST", "").strip()
    user = os.environ.get("PREGRADER_SMTP_USER", "").strip()
    password = os.environ.get("PREGRADER_SMTP_PASSWORD", "")
    recipients = [a.strip() for a in os.environ.get("PREGRADER_NOTIFY_TO", "").split(",") if a.strip()]
    if not (host and user and password and recipients):
        return None
    try:
        port = int(os.environ.get("PREGRADER_SMTP_PORT", "587"))
    except ValueError:
        port = 587
    sender = os.environ.get("PREGRADER_NOTIFY_FROM", "").strip() or user
    return {"host": host, "port": port, "user": user, "password": password,
            "sender": sender, "recipients": recipients}


def build_message(username: str, ip: str) -> str:
    # El usuario es texto libre en el login: se limpia para no inyectar contenido en el aviso.
    safe_user = re.sub(r"[^\w.@+-]", "", username or "")[:40] or "?"
    safe_ip = re.sub(r"[^0-9a-fA-F.:]", "", ip or "")[:45] or "?"
    return f"Academic Pregrader: inicio de sesión de {safe_user} desde {safe_ip}"


def _send(cfg: dict, text: str) -> None:
    try:
        msg = EmailMessage()
        msg["Subject"] = text
        msg["From"] = cfg["sender"]
        msg["To"] = ", ".join(cfg["recipients"])
        msg.set_content(text)
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
    except Exception:
        log.exception("No se pudo enviar el aviso de inicio de sesión")


def notify_login(username: str, ip: str) -> bool:
    """Dispara el aviso en segundo plano. Devuelve True si se programó el envío."""
    cfg = _config()
    if not cfg:
        return False
    threading.Thread(target=_send, args=(cfg, build_message(username, ip)), daemon=True).start()
    return True
