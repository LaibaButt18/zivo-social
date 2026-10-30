import html
import os
import smtplib
import threading
from email.message import EmailMessage

EMAILABLE_KINDS = frozenset({"follow", "friend", "group", "chat", "webinar", "blog"})


def smtp_ready():
    return bool(os.environ.get("SMTP_USER", "").strip() and os.environ.get("SMTP_PASSWORD", "").strip())


def app_base_url():
    return os.environ.get("APP_BASE_URL", "http://127.0.0.1:5000").rstrip("/")


def absolute_url(href):
    href = "" if href is None else str(href).strip()
    if href == "":
        return app_base_url()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return app_base_url() + href
    return app_base_url() + "/" + href


def _from_header():
    user = os.environ.get("SMTP_USER", "").strip()
    name = os.environ.get("SMTP_FROM_NAME", "Zivo").strip() or "Zivo"
    return "%s <%s>" % (name, user)


def _wrap_html(title, body_html, button_label="", button_url=""):
    button = ""
    if button_label and button_url:
        button = (
            '<p style="margin:28px 0 0;">'
            '<a href="%s" style="display:inline-block;background:#1d9bf0;color:#fff;'
            'text-decoration:none;padding:12px 20px;border-radius:999px;font-weight:700;">%s</a></p>'
        ) % (html.escape(button_url, quote=True), html.escape(button_label))
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:24px;background:#f7f9f9;'
        'font-family:Inter,Helvetica,Arial,sans-serif;color:#0f1419;">'
        '<div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #eff3f4;'
        'border-radius:16px;padding:28px 24px;">'
        '<p style="margin:0 0 16px;font-size:18px;font-weight:800;">Zivo</p>'
        '<h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;">%s</h1>'
        '%s%s'
        '<p style="margin:28px 0 0;font-size:13px;color:#536471;">Sent by Zivo</p>'
        "</div></body></html>"
    ) % (html.escape(title), body_html, button)


def send_email(to, subject, text, html_body=None):
    to = "" if to is None else str(to).strip().lower()
    subject = "" if subject is None else str(subject).strip()
    text = "" if text is None else str(text)
    if to == "" or subject == "" or text == "":
        return False
    if not smtp_ready():
        print("mail: SMTP is not configured; skipped email to %s" % to, flush=True)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _from_header()
    message["To"] = to
    message.set_content(text)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    try:
        port = int(os.environ.get("SMTP_PORT", "587") or 587)
    except ValueError:
        port = 587
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")

    def deliver():
        try:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(message)
            print("mail: sent %s to %s" % (subject, to), flush=True)
        except Exception as err:
            print("mail: failed %s to %s: %s" % (subject, to, err), flush=True)

    thread = threading.Thread(target=deliver, daemon=True)
    thread.start()
    return True


def send_password_reset(to, name, link):
    name = (name or "there").strip() or "there"
    subject = "Reset your Zivo password"
    text = (
        "Hi %s,\n\n"
        "Use this link to choose a new Zivo password. It expires in 30 minutes.\n\n"
        "%s\n\n"
        "If you did not ask for this, you can ignore this email.\n"
    ) % (name, link)
    body = (
        '<p style="margin:0;font-size:15px;line-height:1.5;">Hi %s,</p>'
        '<p style="margin:12px 0 0;font-size:15px;line-height:1.5;">'
        "Use the button below to choose a new password. This link expires in 30 minutes.</p>"
        '<p style="margin:12px 0 0;font-size:13px;color:#536471;line-height:1.5;">'
        "If you did not ask for this, you can ignore this email.</p>"
    ) % html.escape(name)
    return send_email(to, subject, text, _wrap_html(subject, body, "Choose a new password", link))


def send_password_changed(to, name):
    name = (name or "there").strip() or "there"
    subject = "Your Zivo password was changed"
    login = absolute_url("loginpage.html")
    text = (
        "Hi %s,\n\n"
        "Your Zivo password was changed successfully. You can sign in here:\n\n"
        "%s\n\n"
        "If you did not do this, reset your password right away.\n"
    ) % (name, login)
    body = (
        '<p style="margin:0;font-size:15px;line-height:1.5;">Hi %s,</p>'
        '<p style="margin:12px 0 0;font-size:15px;line-height:1.5;">'
        "Your Zivo password was changed successfully.</p>"
        '<p style="margin:12px 0 0;font-size:13px;color:#536471;line-height:1.5;">'
        "If you did not do this, reset your password right away.</p>"
    ) % html.escape(name)
    return send_email(to, subject, text, _wrap_html(subject, body, "Sign in", login))


def send_welcome(to, name):
    name = (name or "there").strip() or "there"
    subject = "Welcome to Zivo"
    home = absolute_url("feed.html")
    text = (
        "Hi %s,\n\n"
        "Welcome to Zivo. Your account is ready.\n\n"
        "%s\n"
    ) % (name, home)
    body = (
        '<p style="margin:0;font-size:15px;line-height:1.5;">Hi %s,</p>'
        '<p style="margin:12px 0 0;font-size:15px;line-height:1.5;">'
        "Welcome to Zivo. Your account is ready.</p>"
    ) % html.escape(name)
    return send_email(to, subject, text, _wrap_html(subject, body, "Open Zivo", home))


def send_activity_email(to, name, text, href=""):
    name = (name or "there").strip() or "there"
    text = "" if text is None else str(text).strip()
    if text == "":
        return False
    subject = "New activity on Zivo"
    link = absolute_url(href) if href else absolute_url("notifications.html")
    plain = "Hi %s,\n\n%s\n\nOpen Zivo:\n%s\n" % (name, text, link)
    body = (
        '<p style="margin:0;font-size:15px;line-height:1.5;">Hi %s,</p>'
        '<p style="margin:12px 0 0;font-size:15px;line-height:1.5;">%s</p>'
    ) % (html.escape(name), html.escape(text))
    return send_email(to, subject, plain, _wrap_html(subject, body, "Open", link))
