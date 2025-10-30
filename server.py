# server.py

import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    """Monitor को सिर्फ एक बार background thread में चलाओ"""
    global _started
    if not _started:
        # import यहीं करो ताकि app स्टार्ट होते समय block न हो
        import importlib
        main = importlib.import_module("main")
        t = threading.Thread(target=main.main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def health():
    # सिर्फ health OK लौटाओ (यहां monitor मत शुरू करो)
    return "OK - Paaie monitor running", 200

@app.route("/start")
def start_route():
    # जब चाहो monitor शुरू कर सकते हो
    start_monitor_once()
    return "Monitor started", 200
