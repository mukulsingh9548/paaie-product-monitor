#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random
import requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== CONFIG (ENV) =====================
PRODUCT_URL  = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
CHECK_INTERVAL = int(os.getenv("POLL_SECONDS", "120"))
STATE_FILE   = os.getenv("STATE_FILE", "/data/product_state.json")
TIMEOUT      = (15, 60)

EMAIL_TO   = os.getenv("EMAIL_TO", "prakharsharma1360@gmail.com")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_TO)
SMTP_USER  = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS  = os.getenv("SMTP_PASS")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": os.getenv("USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# ===================== HTTP session with retry =====================
def make_session():
    s = requests.Session()
    # urllib3 v1/v2 compatible
    retry_kwargs = dict(total=7, connect=4, read=4, backoff_factor=2,
                        status_forcelist=[429,500,502,503,504])
    try:
        retry = Retry(allowed_methods=["GET"], **retry_kwargs)
    except TypeError:
        retry = Retry(method_whitelist=["GET"], **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter); s.mount("http://", adapter)
    return s

session = make_session()

# ===================== STATE =====================
def _state_dir():
    d = os.path.dirname(STATE_FILE) or "."
    return d

def load_state():
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("state load err:", e)
    return {"qty": None, "in_stock": None}

def save_state(state):
    os.makedirs(_state_dir(), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ===================== NOTIFIERS =====================
def send_email(subject, body):
    if not (SMTP_USER and SMTP_PASS and EMAIL_TO):
        print("Email not configured; skipping"); return
    recipients = [r.strip() for r in str(EMAIL_TO).split(",") if r.strip()]
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM or SMTP_USER
    msg["To"]      = ", ".join(recipients)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ctx); s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(msg["From"], recipients, msg.as_string())
    print(f"Email sent → {recipients}")

def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("Telegram not configured; skipping"); return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Telegram failed:", e)

def notify(title, old_qty, new_qty, in_stock: bool):
    lines = [
        title,
        f"URL: {PRODUCT_URL}",
        f"Quantity: {old_qty} → {new_qty}",
        "Status: " + ("IN STOCK ✅" if in_stock else "OUT OF STOCK ⛔"),
    ]
    body = "\n".join(lines)
    send_email(f"[Paaie] {title}", body)
    send_telegram(body)

# ===================== PARSERS =====================
QTY_PATTERNS = [
    re.compile(r"Hurry[^0-9]{0,20}(\d+)\s*(?:left|remaining)", re.I),
    re.compile(r"Only\s*(\d+)\s*left", re.I),
    re.compile(r"\b(\d+)\s*left\b", re.I),
]

def extract_shopify_handle(product_url: str):
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    if not m: raise ValueError("Product handle not found in URL")
    return base, m.group(1)

def try_shopify_json(product_url: str):
    base, handle = extract_shopify_handle(product_url)
    try:
        p_res = session.get(f"{base}/products/{handle}.js", headers=HEADERS, timeout=TIMEOUT)
        p_res.raise_for_status()
        p_json = p_res.json()
        variants = p_json.get("variants") or []
        if not variants: return None, None
        variant = next((v for v in variants if v.get("available")), variants[0])
        vid = variant["id"]
        v_res = session.get(f"{base}/variants/{vid}.json", headers=HEADERS, timeout=TIMEOUT)
        if v_res.status_code == 200:
            vj = v_res.json().get("variant", {})
            qty = vj.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0: qty = 0
            available = bool(vj.get("available", False))
            return qty, available
        else:
            available = any(v.get("available") for v in variants)
            return None, bool(available)
    except Exception as e:
        print("JSON route failed:", e)
        return None, None

def parse_html_quantity(html: str):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip().lower()
    qty = None
    for pat in QTY_PATTERNS:
        m = pat.search(text)
        if m:
            try: qty = int(m.group(1)); break
            except Exception: pass
    stock_hints = ("in stock", "add to cart", "buy now", "add to bag", "checkout")
    in_stock = any(s in text for s in stock_hints)
    return qty, in_stock

def get_quantity_and_stock(product_url: str):
    qty, in_stock = try_shopify_json(product_url)
    if qty is not None or in_stock is not None:
        print(f"JSON route → qty={qty}, in_stock={in_stock}")
        return qty, in_stock
    print("Falling back to HTML parsing…")
    r = session.get(product_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    print(f"HTML status={r.status_code}, len={len(r.text)}")
    sample = re.sub(r"\s+", " ", r.text[:800])
    print("HTML sample:", sample[:300], "…")
    r.raise_for_status()
    qty, in_stock = parse_html_quantity(r.text)
    print(f"HTML route → qty={qty}, in_stock={in_stock}")
    return qty, in_stock

# ===================== MONITOR LOOP =====================
def main():
    print("Paaie product monitor started…")
    print(f"URL: {PRODUCT_URL}")
    st = load_state()
    prev_qty, prev_stock = st.get("qty"), st.get("in_stock")
    print(f"Last state → qty: {prev_qty} | in_stock: {prev_stock}")
    first_notify = os.getenv("FIRST_NOTIFY", "1") == "1"

    while True:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            print(f"Now → qty: {qty} | in_stock: {in_stock} | last qty: {prev_qty} | last stock: {prev_stock}")

            if prev_qty is None and first_notify and (qty is not None or in_stock is not None):
                notify("Initial quantity observed" if qty is not None else "Initial stock observed",
                       None, qty, bool(in_stock))
            elif qty is not None and qty != prev_qty:
                title = "Product is OUT OF STOCK" if qty == 0 else "Product quantity updated"
                notify(title, prev_qty, qty, qty > 0)
            elif in_stock is not None and prev_stock is not None and in_stock != prev_stock:
                notify("Product Back in Stock" if in_stock else "Product is OUT OF STOCK",
                       prev_qty, qty, bool(in_stock))

            prev_qty, prev_stock = qty, in_stock
            save_state({"qty": prev_qty, "in_stock": prev_stock})

        except requests.exceptions.RequestException as e:
            print("Network error:", e)
        except Exception as e:
            print("Error:", e)

        time.sleep(max(10, CHECK_INTERVAL + random.uniform(-3, 3)))

if __name__ == "__main__":
    main()
