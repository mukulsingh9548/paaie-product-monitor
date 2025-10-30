import requests, time, smtplib, os, json, re
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== CONFIG ==========
PRODUCT_URL = "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing"

EMAIL_TO   = "mukulsinghypm22@gmail.com"
EMAIL_FROM = "mukulsinghypm22@gmail.com"
SMTP_USER  = "mukulsinghypm22@gmail.com"
SMTP_PASS  = os.getenv("SMTP_PASS", "lmcferkpowyayiyc")  # Gmail App Password

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8333104134:AAFGZ-0RoSMCded4h0tPRu7NvwWQuZPOams")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5042966410")

CHECK_INTERVAL = 60   # seconds
STATE_FILE = "product_state.json"

# ========== HTTP SESSION ==========
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
}
def make_session():
    s = requests.Session()
    retry = Retry(total=7, connect=4, read=4, backoff_factor=2,
                  status_forcelist=[429,500,502,503,504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    return s
session = make_session()
TIMEOUT = (15, 60)

# ========== HELPERS ==========
def load_state():
    if not os.path.exists(STATE_FILE): return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ========== ALERTS ==========
def send_email(subject, body):
    """Send email notification"""
    if not SMTP_PASS or "PUT_YOUR_16_CHAR_APP_PASSWORD_HERE" in SMTP_PASS:
        print("⚠️ Set SMTP_PASS to your Gmail App Password before running.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, EMAIL_FROM, EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    print("📩 Email sent to", EMAIL_TO)

def send_telegram(message):
    """Send Telegram message"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        r = requests.post(url, json=data, timeout=15)
        if r.status_code == 200:
            print("💬 Telegram notification sent.")
        else:
            print(f"⚠️ Telegram error {r.status_code}: {r.text}")
    except Exception as e:
        print("❌ Telegram failed:", e)

def notify_all(subject, text):
    """Send both email & Telegram alerts"""
    send_email(subject, text)
    send_telegram(f"{subject}\n\n{text}")

# ========== SCRAPER ==========
def get_product_info():
    print("➡️  Fetching Paai page…")
    r = session.get(PRODUCT_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # --- quantity detection ---
    m = re.search(r"(?:Qty|Quantity)\s*[:\-]?\s*(\d+)", text, flags=re.I)
    qty = int(m.group(1)) if m else None

    # --- stock detection ---
    in_stock = any(x in text for x in ["Add to Cart", "In Stock", "Add to Cart Online"])

    print("📊 Parsed -> Qty:", qty, "| In stock:", in_stock)
    return qty, in_stock

# ========== MONITOR LOOP ==========
def main():
    print("🚀 Product Monitor started...")
    while True:
        try:
            qty, in_stock = get_product_info()
            state = load_state()
            last_qty   = state.get("qty")
            last_stock = state.get("in_stock")

            print(f"Current Qty: {qty} | Last Qty: {last_qty} | In stock: {in_stock}")

            # --- Quantity increased ---
            if qty is not None and (last_qty is None or qty > last_qty):
                notify_all("🔔 Quantity Increased!",
                           f"Quantity increased from {last_qty} → {qty}\n{PRODUCT_URL}")

            # --- Back in stock ---
            if in_stock and (last_stock in (None, False)):
                notify_all("🟢 Product Back in Stock!",
                           f"The product appears available now.\n{PRODUCT_URL}")

            # --- Out of stock or zero quantity ---
            if (qty == 0 or not in_stock) and (last_stock not in (False, None) or (last_qty is not None and last_qty != 0)):
                notify_all("🔴 Product Out of Stock!",
                           f"The product is out of stock or quantity is now 0.\n{PRODUCT_URL}")

            # save state
            state["qty"] = qty
            state["in_stock"] = in_stock
            save_state(state)

        except Exception as e:
            print("⚠️ Error:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
