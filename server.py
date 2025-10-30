# server.py
import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        # >>> IMPORT यहीं करो ताकि app import होते समय block ना हो
        from main import main as monitor_main
        t = threading.Thread(target=monitor_main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def health():
    # हर हिट पर ensure कि बैकग्राउंड थ्रेड चल रहा है
    start_monitor_once()
    return "OK - Paaie monitor running", 200
