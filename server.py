import threading, signal, sys, os, requests, smtplib, ssl
from flask import Flask, Response
from email.message import EmailMessage

app = Flask(__name__)
_started = False  # ensure single start per process

# ------------------------------- background monitor ------------------------
def start_monitor_once():
    """Start product monitor only once."""
    global _started
    if _started:
        return
    try:
        from main import main as monitor_main
        t = threading.Thread(target=monitor_main, daemon=True)
        t.start()
        _started = True
        print("✅ Product monitor thread started successfully.")
    except Exception as e:
        print(f"❌ Error starting monitor: {e}")

# ------------------------------- routes ------------------------------------
@app.route("/")
def index():
    start_monitor_once()
    return Response("✅ Paaie product monitor is running fine!", status=200, mimetype="text/plain")

@app.route("/healthz")
def healthz():
    # make sure monitor has started for this process
    start_monitor_once()
    return {"ok": True}, 200

def _send_email_safe(subject: str, body: str):
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    mail_to   = os.environ.get("EMAIL_TO") or os.environ.get("MAIL_TO")
    host      = os.environ.get("SMTP_HOST", "smtp.gmail.com")

    if not (smtp_user and smtp_pass and mail_to):
        print("[TEST_NOTIFY] ⚠️ Email skipped (missing env vars).")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = mail_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, 587, timeout=10) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        print("[TEST_NOTIFY] ✅ Email sent via 587 STARTTLS.")
        return
    except Exception as e:
        print(f"[TEST_NOTIFY] 587 failed: {e}; retrying 465/SSL...")

    try:
        with smtplib.SMTP_SSL(host, 465, context=ssl.create_default_context(), timeout=10) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        print("[TEST_NOTIFY] ✅ Email sent via 465 SSL.")
    except Exception as e2:
        print(f"[TEST_NOTIFY] ❌ Email failed on both ports: {e2}")

@app.route("/_test_notify")
def _test_notify():
    try:
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        tg_chat  = os.environ.get("TELEGRAM_CHAT_ID")

        if tg_token and tg_chat:
            tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            r = requests.post(
                tg_url,
                json={"chat_id": tg_chat, "text": "✅ TEST: Paaie monitor notification working!"},
                timeout=10,
            )
            print(f"[TEST_NOTIFY] Telegram status: {r.status_code}")
        else:
            print("[TEST_NOTIFY] ⚠️ Telegram skipped (missing env vars).")

        _send_email_safe(
            "[Paaie] TEST Notification",
            "✅ Your Paaie monitor test email works perfectly!"
        )

        return Response("✅ Test notification executed (check Telegram and email).",
                        status=200, mimetype="text/plain")
    except Exception as e:
        print(f"❌ Error in test notify: {e}")
        return Response(f"❌ Error: {e}", status=500, mimetype="text/plain")

# ------------------------------- graceful exit -----------------------------
def _graceful_exit(*_):
    print("🛑 Shutting down...")
    sys.exit(0)

signal.signal(signal.SIGTERM, _graceful_exit)
signal.signal(signal.SIGINT, _graceful_exit)

# ------------------------------- local run ---------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Starting Flask server on port {port}")
    start_monitor_once()
    app.run(host="0.0.0.0", port=port)
