#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random, sys, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============== CONFIG ===============
PRODUCT_URL   = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
CHECK_SECONDS = max(10, int(os.getenv("POLL_SECONDS", "120")))
STATE_FILE    = os.getenv("STATE_FILE", "./product_state.json")
FIRST_NOTIFY  = os.getenv("FIRST_NOTIFY", "1") == "1"     # first boot par 1 notification

EMAIL_TO   = os.getenv("EMAIL_TO", "").strip()
EMAIL_FROM = (os.getenv("EMAIL_FROM") or EMAIL_TO.split(",")[0] or "").strip()
SMTP_USER  = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS  = os.getenv("SMTP_PASS")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEOUT = (15, 60)

# If EMAIL_TO blank, set a safe default (so email never gets skipped accidentally)
if not EMAIL_TO:
    EMAIL_TO = "mukulsinghypm22@gmail.com"
    if not EMAIL_FROM:
        EMAIL_FROM = EMAIL_TO
    if not SMTP_USER:
        SMTP_USER = EMAIL_FROM

# =============== HEADERS ===============
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

# =============== HTTP SESSION ===============
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

# =============== STATE ===============
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

# =============== NOTIFIERS ===============
def send_email(subject, body):
    recipients = [r.strip() for r in EMAIL_TO.split(",") if r.strip()]
    if not recipients:
        print("[email] no recipients configured; skipping")
        return

    # PREFER SMTP if configured (Gmail App Password etc); else SendGrid
    if SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"]    = EMAIL_FROM
            msg["To"]      = ", ".join(recipients)
            ctx = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(msg["From"], recipients, msg.as_string())
            print(f"[email] sent via SMTP → {recipients}")
            return
        except Exception as e:
            print("[email] smtp error:", e)

    if SENDGRID_API_KEY:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recipients]}],
                "from": {"email": EMAIL_FROM},   # must be verified Single Sender/domain
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            r = http_post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            print(f"[email] sendgrid status: {r.status_code}")
            return
        except Exception as e:
            print("[email] sendgrid error:", e)

    print("[email] no working email transport; skipped")

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

def subject_for_email(title, in_stock, old_qty, new_qty):
    t = title or "Update"
    if "Out of Stock" in t or in_stock is False:
        return f"🔴 {t}!"
    if "Back in Stock" in t or in_stock is True:
        return f"🟢 {t}!"
    if "Quantity" in t:
        return f"🔔 {t}!"
    return t

def notify(title, old_qty, new_qty, in_stock):
    body = (
        f"{title}\n\n"
        f"URL: {PRODUCT_URL}\n"
        f"Quantity: {old_qty} → {new_qty}\n"
        f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
    )
    send_email(subject_for_email(title, in_stock, old_qty, new_qty), body)
    send_telegram(body)

# =============== PARSERS ===============
HURRY_PATTERNS = [
    re.compile(r"\bHurry[^0-9]{0,40}(\d{1,3}(?:,\d{3})*)\s*(?:left|remain(?:ing)?)", re.I),
    re.compile(r"\bOnly[^0-9]{0,20}(\d{1,3}(?:,\d{3})*)\s*left\b", re.I),
]
SOLD_PATTERNS = [
    re.compile(r"\bsold\s*out\b", re.I),
    re.compile(r"\bout\s*of\s*stock\b", re.I),
    re.compile(r"\bcurrently\s*unavailable\b", re.I),
]

def extract_shopify_handle(product_url: str):
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    return base, (m.group(1) if m else None)

def product_and_variants(product_url: str):
    base, handle = extract_shopify_handle(product_url)
    if not handle:
        return base, None
    p = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
    p.raise_for_status()
    return base, p.json().get("variants") or []

def try_variant_json(product_url: str):
    try:
        base, variants = product_and_variants(product_url)
        if not variants:
            return None, None, None
        v = next((v for v in variants if v.get("available")), variants[0])
        vid = v["id"]
        vres = http_get(f"{base}/variants/{vid}.json", headers=HEADERS)
        qty, available = None, bool(v.get("available"))
        if vres.status_code == 200:
            vj = vres.json().get("variant", {})
            qty = vj.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0:
                qty = 0
            available = bool(vj.get("available", available))
        return vid, qty, available
    except Exception as e:
        print("[variant-json] error:", e)
        return None, None, None

def cart_probe_qty(product_url: str, variant_id: int):
    try:
        base, _ = extract_shopify_handle(product_url)
        ajax = dict(AJAX_HEADERS)
        ajax["Origin"]  = base
        ajax["Referer"] = product_url
        # Clear → Add huge qty → Read → Clear
        http_post(f"{base}/cart/clear.js", headers=ajax)
        http_post(f"{base}/cart/add.js", headers=ajax, data={"id": str(variant_id), "quantity": "999"})
        cart = http_get(f"{base}/cart.js", headers=ajax)
        cart.raise_for_status()
        data = cart.json()
        for item in data.get("items", []):
            if str(item.get("variant_id")) == str(variant_id):
                qty = int(item.get("quantity") or 0)
                http_post(f"{base}/cart/clear.js", headers=ajax)
                return qty
        http_post(f"{base}/cart/clear.js", headers=ajax)
    except Exception as e:
        print("[cart-probe] error:", e)
    return None

def parse_html_hurry(html: str):
    # Strip scripts/styles and tags
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.S|re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()

    # “Only X left / Hurry X left”
    for pat in HURRY_PATTERNS:
        m = pat.search(s)
        if m:
            try:
                q = int(m.group(1).replace(",", ""))
                return q, (q > 0)
            except Exception:
                pass

    # Sold out hints
    if any(p.search(s) for p in SOLD_PATTERNS):
        return 0, False

    # Generic hints
    in_stock = "add to cart" in s.lower() or "in stock" in s.lower()
    return None, (True if in_stock else None)

def get_quantity_and_stock(product_url: str):
    # 1) variant.json
    vid, qty, available = try_variant_json(product_url)
    if qty is not None or available is not None:
        print(f"[route:variant.json] qty={qty} available={available}")
        # If qty unknown but available → 2) cart probe
        if qty is None and available and vid:
            q2 = cart_probe_qty(product_url, vid)
            if isinstance(q2, int):
                qty = q2
        return qty, bool(available if available is not None else (qty and qty > 0))

    # 2) cart probe (no json)
    if vid:
        q2 = cart_probe_qty(product_url, vid)
        if isinstance(q2, int):
            return q2, q2 > 0

    # 3) HTML fallback (Hurry/Only X left OR Sold out)
    print("[route:html] fallback…")
    r = http_get(product_url, headers=HEADERS, allow_redirects=True)
    r.raise_for_status()
    qh, stock_hint = parse_html_hurry(r.text)
    if qh is not None:
        return qh, (qh > 0)
    return None, bool(stock_hint) if stock_hint is not None else None

# =============== MONITOR LOOP ===============
def main():
    print("=== Paaie product monitor started ===")
    print("URL:", PRODUCT_URL)
    st = load_state()
    prev_qty   = st.get("qty")
    prev_stock = st.get("in_stock")

    # bootstrap notification once (if configured)
    if FIRST_NOTIFY:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            notify("Initial observation", prev_qty, qty, bool(in_stock))
            prev_qty, prev_stock = qty, in_stock
            save_state({"qty": prev_qty, "in_stock": prev_stock})
        except Exception as e:
            print("[init] error:", e)

    # loop
    while True:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            print(f"[now] qty={qty} in_stock={in_stock} | last qty={prev_qty} last stock={prev_stock}")

            # Robust change detection
            stock_flip = (in_stock is not None and prev_stock is not None and in_stock != prev_stock)
            qty_changed = (qty is not None and qty != prev_qty)
            qty_zero_now = (qty == 0) or (in_stock is False)

            changed = stock_flip or qty_changed or (prev_qty not in (None, 0) and qty_zero_now)

            title = None
            if qty_zero_now:
                title = "Product Out of Stock"
            elif stock_flip and in_stock:
                title = "Product Back in Stock"
            elif qty_changed:
                if prev_qty is None:
                    title = "Quantity Observed"
                else:
                    title = "Quantity Updated"

            if changed and title:
                notify(title, prev_qty, qty, bool(in_stock))
                prev_qty, prev_stock = qty, in_stock
                save_state({"qty": prev_qty, "in_stock": prev_stock})
            else:
                print("[no-change] no notification")

        except requests.exceptions.RequestException as e:
            # Render free tier sometimes yields transient network issues
            print("[network] error:", e)
        except Exception as e:
            print("[loop] error:", e)

        time.sleep(CHECK_SECONDS + random.uniform(-3, 3))

if __name__ == "__main__":
    main()
