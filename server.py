import threading
from flask import Flask, Response
import os
import requests
import smtplib
import ssl
from email.message import EmailMessage

app = Flask(__name__)

_started = False

# -------------------------------------------------------------------------
# 🔹 Start the product monitor in a background thread
# -------------------------------------------------------------------------
def start_monitor_once():
    global _started
    if not _started:
        try:
            from main import main as monitor_main
            t = threading.Thread(target=monitor_main, daemon=True)
            t.start()
            _started = True
            print("✅ Monitor thread started successfully.")
        except Exception as e:
            print(f"❌ Error starting monitor: {e}")

# -------------------------------------------------------------------------
# 🔹 Home route
# -------------------------------------------------------------------------
@app.route('/')
def index():
    start_monitor_once()
    return "✅ Paaie monitor running fine!", 200

# -------------------------------------------------------------------------
# 🔹 Test route: Sends a Telegram + Email notification
# -------------------------------------------------------------------------
@app.route('/_test_notify')
def _test_notify():
    try:
        # Telegram message
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
        if tg_token and tg_chat:
            tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            r = requests.post(
                tg_url,
                json={"chat_id": tg_chat, "text": "TEST ✅: Paaie monitor notification working!"},
                timeout=15,
            )
            print(f"[TEST_NOTIFY] Telegram status: {r.status_code}")

        # Email message
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        mail_to = os.environ.get("MAIL_TO")

        if smtp_user and smtp_pass and mail_to:
            msg = EmailMessage()
            msg["Subject"] = "[Paaie] TEST Notification"
            msg["From"] = smtp_user
            msg["To"] = mail_to
            msg.set_content("✅ Your Paaie monitor test email works perfectly!")

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            print("[TEST_NOTIFY] Email sent successfully.")

        return Response("✅ Test notification sent successfully!", status=200, mimetype="text/plain")

    except Exception as e:
        print(f"❌ Error in test notify: {e}")
        return Response(f"❌ Error: {e}", status=500, mimetype="text/plain")

# -------------------------------------------------------------------------
# 🔹 Run app
# -------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
