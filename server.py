# server.py

import os
import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        # import yahin karo taaki module import par block na ho
        from main import main as monitor_main
        t = threading.Thread(target=monitor_main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def health():
    start_monitor_once()
    return "OK - Paaie monitor running", 200
