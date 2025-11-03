#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, random, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta, timezone

# ================== CONFIG ==================
PRODUCT_URL   = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
CHECK_SECONDS = max(30, int(os.getenv("POLL_SECONDS", "120")))
STATE_FILE    = os.getenv("STATE_FILE", "./product_state.json")

# Email (SendGrid)
EMAIL_FROM        = os.getenv("EMAIL_FROM")
EMAIL_TO          = os.getenv("EMAIL_TO", "")
SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY")

# Telegram
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Duplicate suppression (minutes)
DEDUP_MINUTES = int(os.getenv("DEDUP_MINUTES", "10"))

# ================== HTTP SESSION ==================
def _make_session():
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

session = _make_session()

def http_get(url, **kw):
    kw.setdefault("timeout", (10, 30))
    return session.get(url, **kw)

def http_post(url, **kw):
    kw.setdefault("timeout", (10, 30))
    return session.post(url, **kw)

# ================== STATE MGMT ==================
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"qty": None, "in_stock": None, "last_key": None, "last_time": None}

def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    except Exception as e:
        print("[state] save error:", e)

def within_dedup(last_key, key, last_time):
    if not last_key or not last_time:
        return False
    try:
        last_dt = datetime.fromisoformat(last_time)
        return (last_key == key) and (datetime.now(timezone.utc) - last_dt < timedelta(minutes=DEDUP_MINUTES))
    except Exception:
        return False

# ================== NOTIFIERS ==================
def send_email(subject, body):
    """Send notification email via SendGrid API"""
    if not (EMAIL_FROM and EMAIL_TO and SENDGRID_API_KEY):
        print("[email] missing config, skipping")
        return
    try:
        payload = {
            "personalizations": [{
                "to": [{"email": e.strip()} for e in EMAIL_TO.split(",") if e.strip()]
            }],
            "from": {"email": EMAIL_FROM},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        r = http_post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
        print("[email] sendgrid status:", r.status_code)
    except Exception as e:
        print("[email] error:", e)

def send_telegram(text):
    """Send notification to Telegram"""
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[tg] missing config, skipping")
        return
    try:
        r = http_post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        )
        print("[tg] status:", r.status_code)
    except Exception as e:
        print("[tg] error:", e)

def notify_once(state, key, title, old_qty, new_qty, in_stock):
    """Avoid duplicate alerts"""
    if within_dedup(state.get("last_key"), key, state.get("last_time")):
        print("[notify] duplicate suppressed:", key)
        return

    body = (
        f"{title}\n\n"
        f"URL: {PRODUCT_URL}\n"
        f"Quantity: {old_qty} → {new_qty}\n"
        f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
    )

    # Send both
    send_email(f"[Paaie] {title}", body)
    send_telegram(body)

    # Update dedup state
    state.update({"last_key": key, "last_time": datetime.now(timezone.utc).isoformat()})
    save_state(state)

# ================== PARSING ==================
HURRY_RE = re.compile(r"(?:Hurry|Only)[^0-9]{0,12}(\d+)\s*(?:left|remaining)", re.I)

def extract_shopify_handle(url):
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    return base, m.group(1) if m else None

def try_shopify_json(url):
    base, handle = extract_shopify_handle(url)
    if not handle:
        return None, None
    try:
        data = http_get(f"{base}/products/{handle}.js").json()
        variants = data.get("variants") or []
        if not variants:
            return None, None
        v = variants[0]
        qty = v.get("inventory_quantity")
        if isinstance(qty, int) and qty < 0:
            qty = 0
        avail = bool(v.get("available"))
        return qty, avail
    except Exception as e:
        print("[shopify-json] error:", e)
        return None, None

def parse_html_for_hurry(html):
    """Detect 'Hurry/Only X left' or 'In Stock' signals."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    qty = None
    m = HURRY_RE.search(text)
    if m:
        try:
            qty = int(m.group(1))
        except Exception:
            qty = None
    in_stock = ("in stock" in text.lower()) or ("add to cart" in text.lower())
    return qty, in_stock

def get_stock_info(url):
    """Combine multiple detection methods"""
    qty, stock = try_shopify_json(url)
    if qty is None:
        try:
            r = http_get(url)
            h_qty, h_stock = parse_html_for_hurry(r.text)
            if h_qty is not None:
                qty = h_qty
            if stock is None:
                stock = h_stock
        except Exception as e:
            print("[html] error:", e)
    stock = bool(stock or (isinstance(qty, int) and qty > 0))
    return qty, stock

# ================== MAIN LOOP ==================
def main():
    print("=== Paaie Product Monitor Started ===")
    print("Product:", PRODUCT_URL)
    state = load_state()
    prev_qty, prev_stock = state.get("qty"), state.get("in_stock")
    print(f"Last State → qty={prev_qty}, stock={prev_stock}")

    while True:
        try:
            qty, stock = get_stock_info(PRODUCT_URL)
            print(f"[check] qty={qty} stock={stock} | last qty={prev_qty}, last stock={prev_stock}")

            changed, title, key = False, None, None

            # Stock change?
            if (stock is not None) and (stock != prev_stock):
                changed = True
                title = "Product Back in Stock" if stock else "Product Out of Stock"
                key = f"stock:{int(stock)}"

            # Quantity change?
            if (qty is not None) and (qty != prev_qty):
                changed = True
                title = title or ("Quantity Updated!" if qty > 0 else "Product Out of Stock")
                key = key or f"qty:{qty}"

            if changed:
                notify_once(state, key, title, prev_qty, qty, stock)
                prev_qty, prev_stock = qty, stock
                state["qty"], state["in_stock"] = prev_qty, prev_stock
                save_state(state)
            else:
                print("[no-change] stable")

        except Exception as e:
            print("[loop error]", e)

        time.sleep(CHECK_SECONDS + random.uniform(-3, 3))

if __name__ == "__main__":
    main()
