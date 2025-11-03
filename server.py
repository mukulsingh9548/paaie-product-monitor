#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random, sys, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== CONFIG =====================
PRODUCT_URL    = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
CHECK_INTERVAL = max(10, int(os.getenv("POLL_SECONDS", "120")))
STATE_FILE     = os.getenv("STATE_FILE", "./product_state.json")

EMAIL_TO   = os.getenv("EMAIL_TO", "")
EMAIL_FROM = os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or EMAIL_TO.split(",")[0].strip()
SMTP_USER  = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS  = os.getenv("SMTP_PASS")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FIRST_NOTIFY = os.getenv("FIRST_NOTIFY", "0") == "1"   # default off to avoid spam

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
def _load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("[state] load error:", e)
    return {"qty": None, "in_stock": None}

def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print("[state] save error:", e)

# ===================== NOTIFIERS =====================
def send_email(subject, body):
    recipients = [r.strip() for r in str(EMAIL_TO).split(",") if r.strip()]
    if not recipients:
        print("[email] no recipients; skipping")
        return

    # Prefer SendGrid HTTP
    if SENDGRID_API_KEY and EMAIL_FROM:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recipients]}],
                "from": {"email": EMAIL_FROM},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            r = http_post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            print(f"[email] sendgrid status: {r.status_code}")
            if 200 <= r.status_code < 300:
                return
            else:
                print("[email] sendgrid non-2xx, will try SMTP fallback…", r.text[:200])
        except Exception as e:
            print("[email] sendgrid error → SMTP fallback:", e)

    # SMTP fallback
    if not (SMTP_USER and SMTP_PASS and EMAIL_FROM):
        print("[email] SMTP not configured; skipping")
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
        print("[tg] not configured; skipping")
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

# ===================== PARSERS =====================
# covers: "Hurry, Only 5 left!", "Only 2 left", "Hurry! 3 left", etc.
QTY_PATTERNS = [
    re.compile(r"hurry[^0-9]{0,20}only[^0-9]{0,5}(\d+)\s*left", re.I),
    re.compile(r"only\s*(\d+)\s*left", re.I),
    re.compile(r"\b(\d+)\s*left\b", re.I),
    re.compile(r"sold\s+out", re.I),  # to hint OOS when qty missing
]

def extract_shopify_handle(product_url: str):
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    if not m:
        raise ValueError("Product handle not found in URL")
    return base, m.group(1)

def product_js_and_variant(product_url: str):
    base, handle = extract_shopify_handle(product_url)
    p = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
    p.raise_for_status()
    pdata = p.json()
    variants = pdata.get("variants") or []
    if not variants:
        return base, None, None
    v = next((v for v in variants if v.get("available")), variants[0])
    return base, v.get("id"), bool(v.get("available"))

def try_shopify_json(product_url: str):
    try:
        base, handle = extract_shopify_handle(product_url)
        p = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
        p.raise_for_status()
        pdata = p.json()
        variants = pdata.get("variants") or []
        if not variants:
            return None, None
        v = next((v for v in variants if v.get("available")), variants[0])
        vid = v["id"]

        vres = http_get(f"{base}/variants/{vid}.json", headers=HEADERS)
        if vres.status_code == 200:
            vjson = vres.json().get("variant", {})
            qty = vjson.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0:
                qty = 0
            available = bool(vjson.get("available", False))
            return qty, available
        else:
            available = any(v.get("available") for v in variants)
            return None, bool(available)
    except Exception as e:
        print("[shopify-json] failed:", e)
        return None, None

def parse_html_quantity(html: str):
    # very light HTML strip
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip().lower()

    qty = None
    for pat in QTY_PATTERNS[:3]:
        m = pat.search(text)
        if m:
            try:
                qty = int(m.group(1))
                break
            except Exception:
                pass

    # presence of add-to-cart, etc.
    in_stock = any(k in text for k in ["add to cart", "in stock", "buy now", "add to bag"])
    # explicit sold out
    if re.search(QTY_PATTERNS[3], text):
        in_stock = False
    return qty, in_stock

def get_quantity_via_cart_probe(product_url: str, variant_id: int):
    """Gentle cart-probe to estimate available qty; clears cart afterwards."""
    try:
        base, _ = extract_shopify_handle(product_url)
        ajax = dict(AJAX_HEADERS)
        ajax["Origin"] = base
        ajax["Referer"] = product_url

        http_post(f"{base}/cart/clear.js", headers=ajax)
        http_post(f"{base}/cart/add.js", headers=ajax, data={"id": str(variant_id), "quantity": "999"})
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
    # 1) Variant JSON (best)
    qty, in_stock = try_shopify_json(product_url)
    if qty is not None or in_stock is not None:
        print(f"[route:json] qty={qty}, in_stock={in_stock}")
        # If quantity missing but likely available, try cart-probe
        if qty is None and in_stock:
            try:
                base, vid, _ = product_js_and_variant(product_url)
                if vid:
                    q2 = get_quantity_via_cart_probe(product_url, vid)
                    if isinstance(q2, int):
                        qty = q2
            except Exception as e:
                print("[probe after json] error:", e)
        return qty, bool(in_stock or (qty and qty > 0))

    # 2) HTML fallback (for “Hurry, Only X left!” text)
    print("[route:html] fallback…")
    r = http_get(product_url, headers=HEADERS, allow_redirects=True)
    print(f"[html] status={r.status_code}, len={len(r.text)}")
    r.raise_for_status()
    qty, in_stock = parse_html_quantity(r.text)
    print(f"[route:html] qty={qty}, in_stock={in_stock}")

    # 3) If qty still None but product seems available → probe
    if qty is None and in_stock:
        try:
            base, vid, _ = product_js_and_variant(product_url)
            if vid:
                q2 = get_quantity_via_cart_probe(product_url, vid)
                if isinstance(q2, int):
                    qty = q2
        except Exception as e:
            print("[probe after html] error:", e)

    return qty, in_stock

# ===================== MONITOR LOOP =====================
def main():
    print("=== Paaie product monitor started ===")
    print(f"URL: {PRODUCT_URL}")
    state = _load_state()
    prev_qty   = state.get("qty")
    prev_stock = state.get("in_stock")
    sent_start = False

    while True:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            print(f"[now] qty: {qty} | in_stock: {in_stock} | last qty: {prev_qty} | last stock: {prev_stock}")

            changed = (qty != prev_qty) or (in_stock != prev_stock)

            if changed:
                if in_stock and (prev_stock is False or (prev_qty is not None and qty and qty > 0 and qty != prev_qty)):
                    notify("Product Back in Stock" if in_stock else "Product Out of Stock",
                           prev_qty, qty, in_stock)
                else:
                    # qty change while still in stock (Hurry, Only X left!)
                    title = "Quantity Updated" if in_stock else "Product Out of Stock"
                    notify(title, prev_qty, qty, in_stock)
            else:
                # no change → do not spam; only optional first-time info once
                if FIRST_NOTIFY and not sent_start and (qty is not None or in_stock is not None):
                    notify("Initial observation", prev_qty, qty, bool(in_stock))
                    sent_start = True

            prev_qty, prev_stock = qty, in_stock
            _save_state({"qty": prev_qty, "in_stock": prev_stock})

        except requests.exceptions.RequestException as e:
            print("[network] error:", e)
        except Exception as e:
            print("[loop] error:", e)

        time.sleep(CHECK_INTERVAL + random.uniform(-3, 3))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[exit] stopped by user")
        sys.exit(0)
