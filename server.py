import threading
from flask import Flask

app = Flask(__name__)

_started = False

def start_monitor_once():
    global _started
    if not _started:
        try:
            # import ko function ke andar rakha gaya hai
            from main import main as monitor_main
            t = threading.Thread(target=monitor_main, daemon=True)
            t.start()
            _started = True
        except Exception as e:
            print(f"Error starting monitor: {e}")

@app.route('/')
def home():
    start_monitor_once()
    return "✅ Paaie monitor is running fine", 200

if __name__ == "__main__":
    # Local testing ke liye (Render me ye nahi chalega)
    app.run(host="0.0.0.0", port=5000)
