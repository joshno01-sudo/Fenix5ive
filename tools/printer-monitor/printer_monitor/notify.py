"""Notification channels: on-screen popup and email."""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate
from typing import Callable, Optional, Sequence

from .config import EmailSettings
from .models import AlertEvent

log = logging.getLogger(__name__)

# How long to wait for a standalone popup window to appear before assuming it
# will. Long enough for a cold Tk start, short enough not to stall a poll cycle.
POPUP_STARTUP_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


class EmailNotifier:
    def __init__(self, settings: EmailSettings):
        self.settings = settings

    def send_alerts(self, events: Sequence[AlertEvent]) -> None:
        if not events:
            return
        subject = self._subject(events)
        self.send(subject, _plain_body(events), _html_body(events))

    def send(self, subject: str, text: str, html: Optional[str] = None) -> None:
        settings = self.settings
        if not settings.is_configured():
            raise RuntimeError(
                "Email is not configured — set the SMTP server, From address and at "
                "least one recipient in Settings."
            )

        message = EmailMessage()
        prefix = settings.subject_prefix.strip()
        message["Subject"] = f"{prefix} {subject}".strip()
        message["From"] = settings.from_addr
        message["To"] = ", ".join(settings.to_addrs)
        message["Date"] = formatdate(localtime=True)
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")

        password = settings.password_or_env()
        encryption = (settings.encryption or "starttls").lower()
        timeout = settings.timeout

        if encryption == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
            ) as server:
                if settings.username:
                    server.login(settings.username, password)
                server.send_message(message)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as server:
            server.ehlo()
            if encryption == "starttls":
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if settings.username:
                server.login(settings.username, password)
            server.send_message(message)

    def _subject(self, events: Sequence[AlertEvent]) -> str:
        critical = [e for e in events if e.severity == "critical"]
        if len(events) == 1:
            event = events[0]
            level = f" ({event.level_percent:.0f}%)" if event.level_percent is not None else ""
            tag = "CRITICAL — " if event.severity == "critical" else ""
            return f"{tag}{event.printer_name}: {event.subject_name} low{level}"
        printers = sorted({e.printer_name for e in events})
        who = printers[0] if len(printers) == 1 else f"{len(printers)} printers"
        tag = f"{len(critical)} critical, " if critical else ""
        return f"{who}: {tag}{len(events)} supply alerts"


def _plain_body(events: Sequence[AlertEvent]) -> str:
    stamp = datetime.now().strftime("%a %d %b %Y, %I:%M %p")
    lines = ["Printer supply alert", f"Generated {stamp}", ""]
    for event in sorted(events, key=lambda e: (e.severity != "critical", e.printer_name)):
        marker = "[CRITICAL]" if event.severity == "critical" else "[LOW]"
        lines.append(f"{marker} {event.printer_name} — {event.subject_name}")
        lines.append(f"    {event.message}")
        lines.append("")
    lines.append("-- ")
    lines.append("Sent by Printer Monitor")
    return "\n".join(lines)


def _html_body(events: Sequence[AlertEvent]) -> str:
    stamp = datetime.now().strftime("%a %d %b %Y, %I:%M %p")
    rows = []
    for event in sorted(events, key=lambda e: (e.severity != "critical", e.printer_name)):
        critical = event.severity == "critical"
        color = "#c62828" if critical else "#ef6c00"
        label = "CRITICAL" if critical else "LOW"
        level = f"{event.level_percent:.0f}%" if event.level_percent is not None else "—"
        bar = ""
        if event.level_percent is not None and event.kind in ("supply", "tray"):
            width = max(2, min(100, int(event.level_percent)))
            bar = (
                '<div style="background:#eee;border-radius:3px;height:8px;width:120px;'
                'margin-top:4px;overflow:hidden">'
                f'<div style="background:{color};height:8px;width:{width}%"></div></div>'
            )
        rows.append(
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:10px 12px;vertical-align:top">'
            f'<span style="background:{color};color:#fff;font:600 11px/1.6 sans-serif;'
            f'padding:2px 8px;border-radius:10px">{label}</span></td>'
            f'<td style="padding:10px 12px;vertical-align:top;font:14px sans-serif">'
            f"<strong>{_esc(event.printer_name)}</strong><br>{_esc(event.subject_name)}</td>"
            f'<td style="padding:10px 12px;vertical-align:top;font:14px sans-serif">'
            f"{level}{bar}</td>"
            f'<td style="padding:10px 12px;vertical-align:top;font:13px/1.5 sans-serif;color:#444">'
            f"{_esc(event.message)}</td></tr>"
        )
    return f"""<html><body style="margin:0;padding:24px;background:#f6f6f6">
<div style="max-width:760px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;
box-shadow:0 1px 4px rgba(0,0,0,.1)">
  <div style="background:#111;padding:18px 24px">
    <div style="font:600 18px sans-serif;color:#fff">Printer supply alert</div>
    <div style="font:13px sans-serif;color:#aaa;margin-top:4px">{stamp}</div>
  </div>
  <table style="width:100%;border-collapse:collapse">{''.join(rows)}</table>
  <div style="padding:14px 24px;font:12px sans-serif;color:#888;background:#fafafa">
    Sent by Printer Monitor. Thresholds are configurable in Settings.
  </div>
</div></body></html>"""


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Popup
# ---------------------------------------------------------------------------


def show_popup(events: Sequence[AlertEvent], parent=None) -> bool:
    """Show an always-on-top alert window. Returns False when no GUI is available.

    Safe to call from a worker thread only when ``parent`` is None (it then
    spins up its own short-lived Tk root in a dedicated thread). With a
    ``parent``, call it on the Tk main thread.
    """
    if not events:
        return False
    if parent is not None:
        try:
            from .gui.popup import AlertPopup

            AlertPopup(parent, list(events))
            return True
        except Exception:  # noqa: BLE001 - popups must never break monitoring
            log.exception("failed to show alert popup")
            return False

    return _show_popup_standalone(list(events))


def _show_popup_standalone(events: list[AlertEvent]) -> bool:
    """Service mode: own Tk root in a background thread.

    Waits for the window to actually appear before reporting success — on a
    headless box there is no display, and claiming the popup was shown would
    let the alert be de-duplicated away without anyone having seen it.
    """
    settled = threading.Event()
    outcome: dict[str, bool] = {"shown": False}

    def run() -> None:
        try:
            import tkinter as tk

            from .gui.popup import AlertPopup

            root = tk.Tk()
            root.withdraw()
            popup = AlertPopup(root, events, on_close=root.destroy)
            popup.after(15 * 60 * 1000, root.destroy)  # never wedge a service forever
            outcome["shown"] = True
            settled.set()
            root.mainloop()
        except Exception:  # noqa: BLE001
            log.warning("no display available for popup alerts", exc_info=True)
        finally:
            settled.set()  # unblock the caller whichever way it went

    thread = threading.Thread(target=run, name="alert-popup", daemon=True)
    thread.start()
    if not settled.wait(timeout=POPUP_STARTUP_TIMEOUT):
        # Still opening. Assume it will appear rather than re-alerting forever.
        return True
    return outcome["shown"]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class Notifier:
    """Fans an alert batch out to the enabled channels, recording what happened."""

    def __init__(
        self,
        email_settings: EmailSettings,
        popup_enabled: bool = True,
        email_enabled: bool = False,
        popup_hook: Optional[Callable[[Sequence[AlertEvent]], bool]] = None,
    ):
        self.email = EmailNotifier(email_settings)
        self.popup_enabled = popup_enabled
        self.email_enabled = email_enabled
        # The GUI passes a hook that reuses its existing Tk root.
        self.popup_hook = popup_hook

    def dispatch(self, events: Sequence[AlertEvent]) -> dict[str, object]:
        result: dict[str, object] = {"popup": False, "email": False, "errors": []}
        if not events:
            return result

        if self.popup_enabled:
            try:
                hook = self.popup_hook or show_popup
                result["popup"] = bool(hook(events))
            except Exception as exc:  # noqa: BLE001
                log.exception("popup notification failed")
                result["errors"].append(f"Popup: {exc}")  # type: ignore[union-attr]

        if self.email_enabled:
            try:
                self.email.send_alerts(events)
                result["email"] = True
            except Exception as exc:  # noqa: BLE001
                log.error("email notification failed: %s", exc)
                result["errors"].append(f"Email: {exc}")  # type: ignore[union-attr]

        return result

    def send_test_email(self) -> None:
        self.email.send(
            "Test message",
            "This is a test from Printer Monitor.\n\n"
            "If you got this, low-supply alerts will reach you too.",
            "<p style='font:14px sans-serif'>This is a test from "
            "<strong>Printer Monitor</strong>.</p>"
            "<p style='font:14px sans-serif'>If you got this, low-supply alerts "
            "will reach you too.</p>",
        )
