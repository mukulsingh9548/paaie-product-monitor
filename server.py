import threading, signal, sys, os
from flask import Flask, Response

app = Flask(__name__)
_started = False  # ensure single start per process

def start_monitor_once():
    """Start product monitor in background only once."""
    global _started
    if _started:
        return
    try:
        # background loop from main.py
        from main import main as monitor_main
        t = threading.Thread(target=monitor_main, daemon=True)
        t.start()
        _started = True
        print("✅ Product monitor thread started successfully.")
    except Exception as e:
        print(f"❌ Error starting monitor: {e}")

@app.route("/")
def index():
    start_monitor_once()
    return Response("✅ Paaie product monitor is running.", status=200, mimetype="text/plain")

@app.route("/healthz")
def healthz():
    start_monitor_once()
    return {"ok": True}, 200

def _graceful_exit(*_):
    print("🛑 Shutting down...")
    sys.exit(0)

signal.signal(signal.SIGTERM, _graceful_exit)
signal.signal(signal.SIGINT, _graceful_exit)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Starting Flask server on port {port}")
    start_monitor_once()
    app.run(host="0.0.0.0", port=port)
