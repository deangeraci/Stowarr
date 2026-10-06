"""Optional link notifications; recipients decide on the authenticated web page."""
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def notify(request_id, snapshot):
    channels = [x.strip() for x in os.getenv("STOWARR_NOTIFY_CHANNELS", "").split(",") if x.strip()]
    if any(x not in {"email", "webhook"} for x in channels):
        raise ValueError("Supported notification channels: email, webhook")
    if not channels:
        return
    base = os.environ["STOWARR_APPROVAL_URL"].rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Approval URL must be a credential-free origin")
    payload = {"event": "stowarr.approval_requested", "request_id": request_id,
               "title": snapshot["title"], "release_title": snapshot["release_title"],
               "savings_bytes": snapshot["source_size_bytes"] - snapshot["release_size_bytes"],
               "approval_url": base + "/#" + request_id}
    for channel in channels:
        if channel == "email":
            msg = EmailMessage()
            msg["Subject"] = "Stowarr approval: " + snapshot["title"]
            msg["From"] = os.environ["STOWARR_SMTP_FROM"]
            msg["To"] = os.environ["STOWARR_SMTP_TO"]
            msg.set_content("Review staging proposal (approval does not replace media):\n" + json.dumps(payload, indent=2))
            with smtplib.SMTP(os.environ["STOWARR_SMTP_HOST"], int(os.getenv("STOWARR_SMTP_PORT", "587")), timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if os.getenv("STOWARR_SMTP_USER"):
                    smtp.login(os.environ["STOWARR_SMTP_USER"], os.environ["STOWARR_SMTP_PASSWORD"])
                smtp.send_message(msg)
        else:
            url = os.environ["STOWARR_WEBHOOK_URL"]
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Webhook requires HTTPS without URL credentials")
            headers = {"Content-Type": "application/json"}
            if os.getenv("STOWARR_WEBHOOK_TOKEN"):
                headers["Authorization"] = "Bearer " + os.environ["STOWARR_WEBHOOK_TOKEN"]
            request = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
            with build_opener(NoRedirect()).open(request, timeout=15) as response:
                if not 200 <= response.status < 300:
                    raise ValueError("Notification failed; approval remains queued")
