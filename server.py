import threading, signal, sys, os, requests
from flask import Flask, Response

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
    start_monitor_once()
    return {"ok": True}, 200

# ------------------------------- email (SendGrid only) ---------------------
def _send_email_safe(subject: str, body: str):
    sg_key     = os.environ.get("SENDGRID_API_KEY")
    email_to   = os.environ.get("EMAIL_TO") or os.environ.get("MAIL_TO")
    email_from = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER") or email_to

    if not (sg_key and email_from and email_to):
        print("[TEST_NOTIFY] Email skipped (missing SENDGRID_API_KEY/EMAIL_FROM/EMAIL_TO).")
        return

    to_list = [{"email": e.strip()} for e in str(email_to).split(",") if e.strip()]
    payload = {
        "personalizations": [{"to": to_list}],
        "from": {"email": email_from, "name": "Paaie Product Monitor"},
        "reply_to": {"email": email_from},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    try:
        r = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {sg_key}", "Content-Type": "application/json"},
            json=payload, timeout=15
        )
        if 200 <= r.status_code < 300:
            print(f"[TEST_NOTIFY] Email via SendGrid: {r.status_code}")
        else:
            print(f"[TEST_NOTIFY] SendGrid error: {r.status_code} body={r.text}")
    except Exception as e:
        print(f"[TEST_NOTIFY] SendGrid exception: {e}")

# ------------------------------- test route --------------------------------
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
