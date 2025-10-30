# server.py
import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        # ⬇️ import yahin par, taa ki module import time pe crash na ho
        import main
        t = threading.Thread(target=main.main, daemon=True)
        t.start()
        _started = True

@app.route("/")
def health():
    start_monitor_once()
    return "OK - Paaie monitor running", 200
