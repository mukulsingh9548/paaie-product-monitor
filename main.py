#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random, sys, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== CONFIG =====================
PRODUCT_URL   = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
CHECK_INTERVAL= int(os.getenv("POLL_SECONDS", "120"))
STATE_FILE    = os.getenv("STATE_FILE", "./product_state.json")
FIRST_NOTIFY  = os.getenv("FIRST_NOTIFY", "1") == "1"   # initial observation toggle

EMAIL_TO   = os.getenv("EMAIL_TO", "prakharsharma1360@gmail.com")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_TO)          # MUST equal your verified SendGrid Single Sender
SMTP_USER  = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS  = os.getenv("SMTP_PASS")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
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
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "",
    "Referer": "",
}

# ===================== HTTP SESSION =====================
def make_session():
    s = requests.Session()
    retry = Retry(
        total=7, connect=4, read=4, backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
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
    """
    Prefer SendGrid (HTTP). If missing/unavailable, fall back to SMTP.
    """
    sg_key = os.getenv("SENDGRID_API_KEY")
    recipients = [r.strip() for r in str(EMAIL_TO).split(",") if r.strip()]
    from_email = EMAIL_FROM or SMTP_USER

    # ---- SendGrid first ----
    if sg_key and recipients and from_email:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recipients]}],
                "from": {"email": from_email, "name": "Paaie Product Monitor"},
                "reply_to": {"email": from_email},
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
            print(f"[email] sendgrid rejected: {r.text[:500]}")
        except Exception as e:
            print("[email] sendgrid error, will try SMTP fallback:", e)

    # ---- SMTP fallback ----
    if not (SMTP_USER and SMTP_PASS and recipients):
        print("[email] SMTP not configured; skipping")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = ", ".join(recipients)

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(msg["From"], recipients, msg.as_string())
        print(f"[email] sent via SMTP → {recipients}")
    except Exception as e:
        print(f"[email] SMTP failed: {e}")

def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[tg] not configured; skipping")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = http_post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": False})
        print("[tg] status:", r.status_code)
    except Exception as e:
        print("[tg] failed:", e)

def notify(title, old_qty, new_qty, in_stock: bool):
    def fmt(x):
        return "None" if x is None else str(x)
    body = (
        f"{title}\n"
        f"URL: {PRODUCT_URL}\n"
        f"Quantity: {fmt(old_qty)} → {fmt(new_qty)}\n"
        f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
    )
    send_email(f"[Paaie] {title}", body)
    send_telegram(body)

# ===================== PARSING / FETCH =====================
def extract_shopify_handle(product_url: str):
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    return base, (m.group(1) if m else None)

def try_shopify_json(product_url: str):
    """
    Fast path: product.js -> preferred variant -> variants/{id}.json
    Returns (qty:int|None, available:bool|None)
    """
    base, handle = extract_shopify_handle(product_url)
    if not handle:
        return None, None
    try:
        p = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
        p.raise_for_status()
        pdata = p.json()
        variants = pdata.get("variants") or []
        if not variants:
            return None, None
        variant = next((v for v in variants if v.get("available")), variants[0])
        vid = variant["id"]

        vres = http_get(f"{base}/variants/{vid}.json", headers=HEADERS)
        if vres.status_code == 200:
            vjson = vres.json().get("variant", {})
            qty = vjson.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0:
                qty = 0
            avail = bool(vjson.get("available", False))
            return qty, avail
        # fallback: availability from list
        avail = any(v.get("available") for v in variants)
        return None, bool(avail)
    except Exception as e:
        print("[shopify-json] error:", e)
        return None, None

def get_product_and_variant_id(product_url: str):
    base, handle = extract_shopify_handle(product_url)
    if not handle:
        return None, None
    try:
        pdata = http_get(f"{base}/products/{handle}.js", headers=HEADERS).json()
        variants = pdata.get("variants") or []
        if not variants:
            return base, None
        v = next((v for v in variants if v.get("available")), variants[0])
        return base, v.get("id")
    except Exception as e:
        print("[product.js] error:", e)
        return base, None

def get_quantity_via_cart_probe(product_url: str, variant_id: int):
    """
    Gentle cart probe: add 999 of variant, read cart.js (Shopify clamps to available),
    then clear cart. All within one session; does not affect real users.
    """
    base, _ = extract_shopify_handle(product_url)
    ajax = dict(AJAX_HEADERS)
    ajax["Origin"]  = base
    ajax["Referer"] = product_url
    try:
        http_post(f"{base}/cart/clear.js", headers=ajax)
        add = http_post(f"{base}/cart/add.js", headers=ajax, data={"id": str(variant_id), "quantity": "999"})
        if add.status_code not in (200, 302):
            print("[cart] add failed:", add.status_code, add.text[:200])

        cart = http_get(f"{base}/cart.js", headers=ajax)
        cart.raise_for_status()
        for line in cart.json().get("items", []):
            if str(line.get("variant_id")) == str(variant_id):
                qty = int(line.get("quantity") or 0)
                http_post(f"{base}/cart/clear.js", headers=ajax)
                return qty
        http_post(f"{base}/cart/clear.js", headers=ajax)
    except Exception as e:
        print("[cart-probe] error:", e)
    return None

def get_quantity_and_stock(product_url: str):
    # 1) JSON route first
    qty, in_stock = try_shopify_json(product_url)
    if qty is not None or in_stock is not None:
        # if qty unknown but we know which variant, try cart probe once
        if qty is None and (in_stock or in_stock is None):
            base, vid = get_product_and_variant_id(product_url)
            if vid:
                q2 = get_quantity_via_cart_probe(product_url, vid)
                if isinstance(q2, int):
                    qty = q2
        return qty, (in_stock if in_stock is not None else bool(qty and qty > 0))

    # 2) JSON failed → cart probe
    base, vid = get_product_and_variant_id(product_url)
    if vid:
        q2 = get_quantity_via_cart_probe(product_url, vid)
        if isinstance(q2, int):
            return q2, q2 > 0

    # 3) Last resort: HTML text (theme-dependent)
    try:
        r = http_get(product_url, headers=HEADERS, allow_redirects=True)
        r.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).lower()
        # weak signals
        in_stock = any(s in text for s in ("in stock", "add to cart", "buy now"))
        return None, in_stock
    except Exception as e:
        print("[html] error:", e)
        return None, None

# ===================== MONITOR LOOP =====================
def main():
    print("=== Paaie product monitor started ===")
    print(f"URL: {PRODUCT_URL}")
    st = load_state()
    prev_qty, prev_stock = st.get("qty"), st.get("in_stock")
    print(f"[state] last → qty: {prev_qty} | in_stock: {prev_stock}")

    first_sent = False

    while True:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            print(f"[now] qty={qty} | in_stock={in_stock} | last qty={prev_qty} | last stock={prev_stock}")

            # Initial observation (optional)
            if not first_sent and FIRST_NOTIFY and (qty is not None or in_stock is not None):
                notify("Initial observation", prev_qty, qty, bool(in_stock))
                first_sent = True

            # Notify on quantity change
            if (qty is not None and prev_qty is not None and qty != prev_qty):
                title = "Product Out of Stock" if qty == 0 else "Quantity Updated"
                notify(title, prev_qty, qty, qty > 0)

            # Notify on stock flip
            if (in_stock is not None and prev_stock is not None and in_stock != prev_stock):
                notify("Product Back in Stock" if in_stock else "Product Out of Stock",
                       prev_qty, qty, bool(in_stock))

            # Update state
            prev_qty, prev_stock = qty, in_stock
            save_state({"qty": prev_qty, "in_stock": prev_stock})

        except Exception as e:
            print("[loop] error:", e)

        # tiny jitter to avoid sync hitting /429s at exact cadence
        time.sleep(max(10, CHECK_INTERVAL + random.uniform(-3, 3)))

if __name__ == "__main__":
    main()
