from playwright.sync_api import sync_playwright
import smtplib, json, os, re, time, random
from email.mime.text import MIMEText

PRODUCT_URL = "https://www.costco.com/1-oz-gold-bar-pamp-suisse-lady-fortuna-veriscan-new-in-assay.product.4000186760.html"

EMAIL_TO   = "mukulsinghypm22@gmail.com"
EMAIL_FROM = "mukulsinghypm22@gmail.com"
SMTP_USER  = "mukulsinghypm22@gmail.com"
SMTP_PASS  = "YAHAN_APNA_16_CHAR_APP_PASSWORD_DALO"   # <-- Gmail App Password

STATE_FILE = "product_state.json"
CHECK_INTERVAL = 30  # testing: 60

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

def send_email(sub, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = sub, EMAIL_FROM, EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    print("📩 Email sent to", EMAIL_TO)

def extract_info(text: str):
    m = re.search(r"(?:Qty|Quantity)\s*[:\-]?\s*(\d+)", text, flags=re.I)
    qty = int(m.group(1)) if m else None
    in_stock = any(x in text for x in ["Add to Cart", "In Stock", "Add to Cart Online"])
    return qty, in_stock

def open_page_with_fallback(p):
    ua = random.choice(UAS)

    # --- 1) Chromium with stricter flags (HTTP/2 + QUIC off) ---
    try:
        print("🟦 Launching Chromium with HTTP/2 & QUIC disabled …")
        browser = p.chromium.launch(
            headless=True,  # debug ke liye False bhi kar sakte ho
            args=[
                "--disable-http2",
                "--disable-quic",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=ua,
            ignore_https_errors=True,
            locale="en-US",
        )
        page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        print("➡️  goto (Chromium)…")
        page.goto(PRODUCT_URL, timeout=120_000, wait_until="load")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)
        txt = page.inner_text("body")
        browser.close()
        return txt
    except Exception as e:
        print("⚠️ Chromium failed:", e)

    # --- 2) Firefox fallback ---
    try:
        print("🟧 Falling back to Firefox …")
        browser = p.firefox.launch(headless=True)
        ctx = browser.new_context(
            user_agent=ua,
            ignore_https_errors=True,
            locale="en-US",
        )
        page = ctx.new_page()
        print("➡️  goto (Firefox)…")
        page.goto(PRODUCT_URL, timeout=120_000, wait_until="load")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)
        txt = page.inner_text("body")
        browser.close()
        return txt
    except Exception as e:
        print("❌ Firefox also failed:", e)
        raise

print("🚀 Costco Browser-Monitor started…")
while True:
    try:
        with sync_playwright() as p:
            text = open_page_with_fallback(p)

        qty, in_stock = extract_info(text)
        state = load_state()
        last_qty, last_stock = state.get("qty"), state.get("in_stock")
        print(f"📊 Qty: {qty} | Last: {last_qty} | In stock: {in_stock}")

        # Quantity increase
        if qty is not None and (last_qty is None or qty > last_qty):
            send_email("🔔 Quantity Increased!",
                       f"Quantity increased: {last_qty} → {qty}\n{PRODUCT_URL}")

        # Back in stock (first time or OOS->IN)
        if in_stock and (last_stock in (None, False)):
            send_email("🟢 Product Back in Stock!",
                       f"The product is now available!\n{PRODUCT_URL}")

        state["qty"], state["in_stock"] = qty, in_stock
        save_state(state)

    except Exception as e:
        print("🚨 Cycle error:", e)

    print(f"⏳ Waiting {CHECK_INTERVAL} seconds before next check…\n")
    time.sleep(CHECK_INTERVAL)
