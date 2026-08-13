"""Email construction and SMTP handling, with a stand-in SMTP server."""

from __future__ import annotations

import smtplib

import pytest

from printer_monitor.config import EmailSettings
from printer_monitor.models import AlertEvent
from printer_monitor.notify import EmailNotifier, Notifier


class FakeSMTP:
    """Records what the notifier does instead of talking to a real server."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.started_tls = False
        self.login_args = None
        self.messages = []
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.quit_called = True

    def ehlo(self, *_args):
        return 250, b"ok"

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.messages.append(message)


@pytest.fixture(autouse=True)
def clear_instances():
    FakeSMTP.instances.clear()
    yield
    FakeSMTP.instances.clear()


@pytest.fixture
def settings():
    return EmailSettings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        encryption="starttls",
        username="shop@example.com",
        password="secret",
        from_addr="shop@example.com",
        to_addrs=["owner@example.com", "front@example.com"],
        subject_prefix="[Printer Monitor]",
    )


def events(*specs) -> list[AlertEvent]:
    out = []
    for name, severity, percent in specs:
        out.append(
            AlertEvent(
                printer_id="latex360",
                printer_name="HP Latex 360",
                subject_key=name.lower(),
                subject_name=name,
                kind="supply",
                severity=severity,
                message=f"{name} is at {percent}%",
                level_percent=percent,
                threshold=20.0,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Configuration guards
# ---------------------------------------------------------------------------


def test_is_configured():
    assert not EmailSettings().is_configured()
    assert not EmailSettings(smtp_host="h", from_addr="a@b.c").is_configured()
    assert EmailSettings(smtp_host="h", from_addr="a@b.c", to_addrs=["d@e.f"]).is_configured()


def test_sending_without_configuration_raises():
    with pytest.raises(RuntimeError, match="not configured"):
        EmailNotifier(EmailSettings()).send("subject", "body")


def test_env_var_password_wins(monkeypatch, settings):
    monkeypatch.setenv("PRINTER_MONITOR_SMTP_PASSWORD", "from-env")
    assert settings.password_or_env() == "from-env"
    monkeypatch.delenv("PRINTER_MONITOR_SMTP_PASSWORD")
    assert settings.password_or_env() == "secret"


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def test_starttls_flow(monkeypatch, settings):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    EmailNotifier(settings).send_alerts(events(("Cyan", "warning", 15)))

    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.started_tls
    assert server.login_args == ("shop@example.com", "secret")
    assert len(server.messages) == 1


def test_ssl_flow_uses_smtp_ssl(monkeypatch, settings):
    settings.encryption = "ssl"
    settings.smtp_port = 465
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    EmailNotifier(settings).send_alerts(events(("Cyan", "warning", 15)))

    server = FakeSMTP.instances[0]
    assert server.port == 465
    assert not server.started_tls  # SSL wraps the socket instead
    assert server.context is not None


def test_plain_flow_skips_tls(monkeypatch, settings):
    settings.encryption = "none"
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    EmailNotifier(settings).send_alerts(events(("Cyan", "warning", 15)))
    assert not FakeSMTP.instances[0].started_tls


def test_anonymous_relay_does_not_log_in(monkeypatch, settings):
    settings.username = ""
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    EmailNotifier(settings).send_alerts(events(("Cyan", "warning", 15)))
    assert FakeSMTP.instances[0].login_args is None


def test_no_events_sends_nothing(monkeypatch, settings):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    EmailNotifier(settings).send_alerts([])
    assert FakeSMTP.instances == []


# ---------------------------------------------------------------------------
# Message content
# ---------------------------------------------------------------------------


def sent_message(monkeypatch, settings, alert_events):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    EmailNotifier(settings).send_alerts(alert_events)
    return FakeSMTP.instances[0].messages[0]


def test_single_alert_subject(monkeypatch, settings):
    message = sent_message(monkeypatch, settings, events(("Cyan", "warning", 15)))
    assert message["Subject"] == "[Printer Monitor] HP Latex 360: Cyan low (15%)"
    assert message["To"] == "owner@example.com, front@example.com"
    assert message["From"] == "shop@example.com"


def test_critical_subject_is_marked(monkeypatch, settings):
    message = sent_message(monkeypatch, settings, events(("Black", "critical", 4)))
    assert "CRITICAL" in message["Subject"]


def test_multiple_alert_subject_counts_them(monkeypatch, settings):
    message = sent_message(
        monkeypatch, settings, events(("Cyan", "warning", 15), ("Black", "critical", 4))
    )
    assert message["Subject"] == "[Printer Monitor] HP Latex 360: 1 critical, 2 supply alerts"


def test_body_has_plain_and_html_parts(monkeypatch, settings):
    message = sent_message(monkeypatch, settings, events(("Cyan", "warning", 15)))
    assert message.is_multipart()
    types = {part.get_content_type() for part in message.walk()}
    assert "text/plain" in types
    assert "text/html" in types


def test_plain_body_lists_every_alert(monkeypatch, settings):
    message = sent_message(
        monkeypatch, settings, events(("Cyan", "warning", 15), ("Black", "critical", 4))
    )
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert "[CRITICAL] HP Latex 360 — Black" in body
    assert "[LOW] HP Latex 360 — Cyan" in body
    # Critical items come first.
    assert body.index("Black") < body.index("Cyan")


def test_html_body_escapes_markup(monkeypatch, settings):
    nasty = AlertEvent(
        printer_id="p",
        printer_name="<script>alert(1)</script>",
        subject_key="k",
        subject_name="Cyan & Black",
        kind="supply",
        severity="warning",
        message="level < 20%",
        level_percent=15.0,
    )
    message = sent_message(monkeypatch, settings, [nasty])
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Cyan &amp; Black" in html
    assert "level &lt; 20%" in html


def test_subject_prefix_can_be_empty(monkeypatch, settings):
    settings.subject_prefix = ""
    message = sent_message(monkeypatch, settings, events(("Cyan", "warning", 15)))
    assert message["Subject"] == "HP Latex 360: Cyan low (15%)"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_dispatch_calls_both_channels(monkeypatch, settings):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    seen = []
    notifier = Notifier(
        settings,
        popup_enabled=True,
        email_enabled=True,
        popup_hook=lambda evts: seen.append(list(evts)) or True,
    )
    result = notifier.dispatch(events(("Cyan", "warning", 15)))
    assert result["popup"] is True
    assert result["email"] is True
    assert result["errors"] == []
    assert len(seen) == 1


def test_dispatch_reports_email_failure_without_raising(settings, monkeypatch):
    def explode(*_args, **_kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"bad password")

    monkeypatch.setattr(smtplib, "SMTP", explode)
    notifier = Notifier(settings, popup_enabled=False, email_enabled=True)
    result = notifier.dispatch(events(("Cyan", "warning", 15)))
    assert result["email"] is False
    assert any("Email" in str(e) for e in result["errors"])


def test_popup_failure_does_not_block_email(monkeypatch, settings):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    def broken_popup(_events):
        raise RuntimeError("no display")

    notifier = Notifier(
        settings, popup_enabled=True, email_enabled=True, popup_hook=broken_popup
    )
    result = notifier.dispatch(events(("Cyan", "warning", 15)))
    assert result["email"] is True
    assert any("Popup" in str(e) for e in result["errors"])


def test_disabled_channels_do_nothing(monkeypatch, settings):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    notifier = Notifier(settings, popup_enabled=False, email_enabled=False)
    result = notifier.dispatch(events(("Cyan", "warning", 15)))
    assert result == {"popup": False, "email": False, "errors": []}
    assert FakeSMTP.instances == []


def test_test_email_content(monkeypatch, settings):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    Notifier(settings, popup_enabled=False, email_enabled=True).send_test_email()
    message = FakeSMTP.instances[0].messages[0]
    assert "Test message" in message["Subject"]
    assert "test" in message.get_body(preferencelist=("plain",)).get_content().lower()
