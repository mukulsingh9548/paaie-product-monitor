import threading
from flask import Flask
import os

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        try:
            from main import main as monitor_main
            t = threading.Thread(target=monitor_main, daemon=True)
            t.start()
            _started = True
            print("Monitor thread started successfully.")
        except Exception as e:
            print(f"❌ Error starting monitor: {e}")

@app.route('/')
def index():
    start_monitor_once()
    return "✅ Paaie monitor running fine!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
