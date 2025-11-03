#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random, sys, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== CONFIG =====================
PRODUCT_URL = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
CHECK_INTERVAL = int(os.getenv("POLL_SECONDS", "120"))
STATE_FILE = os.getenv("STATE_FILE", "./product_state.json")

EMAIL_TO = os.getenv("EMAIL_TO", "prakharsharma1360@gmail.com")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_TO)
SMTP_USER = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEOUT = (15, 60)

# ===================== HEADERS =====================
HEADERS = {
    "User-Agent": os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

AJAX_HEADERS = {
    **HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

# ===================== HTTP SESSION =====================
def make_session():
    s = requests.Session()
    retry = Retry(total=7, connect=4, read=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

session = make_session()

def http_get(url, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    return session.get(url, **kwargs)

def http_post(url, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    return session.post(url, **kwargs)

# ===================== STATE =====================
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("[state] load error:", e)
    return {"qty": None, "in_stock": None}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print("[state] save error:", e)

# ===================== NOTIFIERS =====================
def send_email(subject, body):
    sg_key = os.getenv("SENDGRID_API_KEY")
    recipients = [r.strip() for r in str(EMAIL_TO).split(",") if r.strip()]
    if sg_key:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recipients]}],
                "from": {"email": EMAIL_FROM},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            r = http_post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {sg_key}", "Content-Type": "application/json"},
                json=payload,
            )
            print(f"[email] sendgrid status: {r.status_code}")
            if 200 <= r.status_code < 300:
                return
        except Exception as e:
            print("[email] sendgrid error:", e)

    # SMTP fallback
    if not (SMTP_USER and SMTP_PASS):
        print("[email] SMTP not configured.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(msg["From"], recipients, msg.as_string())
    print(f"[email] sent via SMTP → {recipients}")

def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[tg] not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = http_post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print("[tg] status:", r.status_code)
    except Exception as e:
        print("[tg] failed:", e)

def notify(title, old_qty, new_qty, in_stock: bool):
    body = (
        f"{title}\n\n"
        f"URL: {PRODUCT_URL}\n"
        f"Quantity: {old_qty} → {new_qty}\n"
        f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
    )
    send_email(f"[Paaie] {title}", body)
    send_telegram(body)

# ===================== PARSING =====================
def extract_shopify_handle(product_url: str):
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    return base, m.group(1) if m else None

def try_shopify_json(product_url: str):
    base, handle = extract_shopify_handle(product_url)
    if not handle: return None, None
    try:
        p = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
        p.raise_for_status()
        pdata = p.json()
        variants = pdata.get("variants") or []
        if not variants: return None, None
        v = next((v for v in variants if v.get("available")), variants[0])
        vid = v["id"]
        vres = http_get(f"{base}/variants/{vid}.json", headers=HEADERS)
        if vres.status_code == 200:
            vjson = vres.json().get("variant", {})
            return vjson.get("inventory_quantity"), vjson.get("available")
    except Exception as e:
        print("[shopify-json] error:", e)
    return None, None

# --- cart probe fallback ---
def get_quantity_via_cart_probe(product_url: str, variant_id: int):
    base, _ = extract_shopify_handle(product_url)
    ajax = dict(AJAX_HEADERS)
    ajax["Origin"] = base
    ajax["Referer"] = product_url
    try:
        http_post(f"{base}/cart/clear.js", headers=ajax)
        http_post(f"{base}/cart/add.js", headers=ajax, data={"id": str(variant_id), "quantity": "999"})
        cart = http_get(f"{base}/cart.js", headers=ajax)
        cart.raise_for_status()
        for item in cart.json().get("items", []):
            if str(item.get("variant_id")) == str(variant_id):
                qty = int(item.get("quantity") or 0)
                http_post(f"{base}/cart/clear.js", headers=ajax)
                return qty
        http_post(f"{base}/cart/clear.js", headers=ajax)
    except Exception as e:
        print("[cart-probe] error:", e)
    return None

# --- main fetcher ---
def get_quantity_and_stock(product_url: str):
    qty, in_stock = try_shopify_json(product_url)
    base, handle = extract_shopify_handle(product_url)
    if not handle:
        return qty, in_stock
    try:
        pdata = http_get(f"{base}/products/{handle}.js", headers=HEADERS).json()
        variants = pdata.get("variants") or []
        vid = next((v["id"] for v in variants if v.get("available")), variants[0]["id"])
        if qty is None:
            q2 = get_quantity_via_cart_probe(product_url, vid)
            if q2 is not None: qty = q2
    except Exception as e:
        print("[variant probe] error:", e)
    return qty, bool(in_stock or (qty and qty > 0))

# ===================== MONITOR LOOP =====================
def main():
    print("=== Paaie product monitor started ===")
    st = load_state()
    prev_qty, prev_stock = st.get("qty"), st.get("in_stock")
    while True:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            print(f"[now] qty={qty}, in_stock={in_stock}, last={prev_qty}")
            if qty != prev_qty or in_stock != prev_stock:
                title = "Product Back in Stock" if in_stock else "Product Out of Stock"
                notify(title, prev_qty, qty, in_stock)
            else:
                notify("No Change Detected", prev_qty, qty, in_stock)
            save_state({"qty": qty, "in_stock": in_stock})
        except Exception as e:
            print("[loop] error:", e)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
