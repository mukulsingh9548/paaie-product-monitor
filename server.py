# server.py
import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        # Import here so any heavy/env-reading code runs in the background thread,
        # not at app import time.
        import main as monitor_main
        t = threading.Thread(target=monitor_main.main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def health():
    start_monitor_once()
    return "OK - Paaie monitor running", 200
