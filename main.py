import requests, time, smtplib, os, json, re
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== CONFIG ==========
PRODUCT_URL = "https://www.costco.com/1-oz-gold-bar-pamp-suisse-lady-fortuna-veriscan-new-in-assay.product.4000186760.html"

EMAIL_TO   = "mukulsinghypm22@gmail.com"
EMAIL_FROM = "mukulsinghypm22@gmail.com"
SMTP_USER  = "mukulsinghypm22@gmail.com"
SMTP_PASS  = os.getenv("SMTP_PASS", "PUT_YOUR_16_CHAR_APP_PASSWORD_HERE")  # <-- App Password

CHECK_INTERVAL = 60   # testing: 60s; stable: 1800 (30 min)
STATE_FILE = "product_state.json"

# ========== HTTP SESSION ==========
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "close",
}
def make_session():
    s = requests.Session()
    retry = Retry(total=7, connect=4, read=4, backoff_factor=2,
                  status_forcelist=[429,500,502,503,504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter); s.mount("http://", adapter)
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

def send_email(subject, body):
    if not SMTP_PASS or "PUT_YOUR_16_CHAR_APP_PASSWORD_HERE" in SMTP_PASS:
        print("⚠️ Set SMTP_PASS to your Gmail App Password before running.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, EMAIL_FROM, EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    print("📩 Email sent to", EMAIL_TO)

# ========== SCRAPER ==========
def get_product_info():
    print("➡️  Fetching Costco page…")
    r = session.get(PRODUCT_URL, headers=HEADERS, timeout=TIMEOUT)
    print("✅ Response:", r.status_code, "| Size:", len(r.content))
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # --- quantity detection (best-effort) ---
    m = re.search(r"(?:Qty|Quantity)\s*[:\-]?\s*(\d+)", text, flags=re.I)
    qty = int(m.group(1)) if m else None

    # --- stock detection ---
    in_stock = any(x in text for x in ["Add to Cart", "In Stock", "Add to Cart Online"])
    print("📊 Parsed -> Qty:", qty, "| In stock:", in_stock)
    return qty, in_stock

# ========== (OPTIONAL) one-time SMTP test ==========
# send_email("Test ✅", "SMTP working. Alerts will be sent on quantity increase or when back in stock.")

# ========== MONITOR LOOP ==========
print("🚀 Costco Product Monitor started...")

while True:
    try:
        qty, in_stock = get_product_info()

        state = load_state()
        last_qty   = state.get("qty")
        last_stock = state.get("in_stock")

        print(f"Current Qty: {qty} | Last Qty: {last_qty} | In stock: {in_stock}")

        # --- Quantity increased (or first time we saw a number) ---
        if qty is not None and (last_qty is None or qty > last_qty):
            send_email("🔔 Quantity Increased!",
                       f"Quantity increased from {last_qty} → {qty}\n{PRODUCT_URL}")

        # --- Back in stock (first ever or OOS -> IN) ---
        if in_stock and (last_stock in (None, False)):
            send_email("🟢 Product Back in Stock!",
                       f"The product appears available now.\n{PRODUCT_URL}")

        # save state
        state["qty"] = qty
        state["in_stock"] = in_stock
        save_state(state)

    except requests.exceptions.Timeout:
        print("⏳ Timeout – will retry next cycle.")
    except requests.exceptions.RequestException as e:
        print("⚠️ Network error:", e)
    except Exception as e:
        print("❌ Other error:", e)

    time.sleep(CHECK_INTERVAL)
