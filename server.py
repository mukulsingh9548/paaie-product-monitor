import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        # Import yahin par karo, upar nahi
        from main import main as monitor_main
        t = threading.Thread(target=monitor_main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def home():
    start_monitor_once()
    return "✅ Paaie monitor is running fine", 200
