# server.py
import os
import threading
from flask import Flask

import main  # main.py me jo main() infinite loop hai

app = Flask(__name__)

_started = False
def start_monitor_once():
    global _started
    if not _started:
        t = threading.Thread(target=main.main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def health():
    start_monitor_once()
    return "OK - Paaie monitor running", 200
