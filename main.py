#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============== CONFIG ===============
PRODUCT_URL   = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
POLL_SECONDS  = max(10, int(os.getenv("POLL_SECONDS", "120")))
STATE_FILE    = os.getenv("STATE_FILE", "./product_state.json")
FIRST_NOTIFY  = os.getenv("FIRST_NOTIFY", "1") == "1"   # first start par ek snapshot alert

# Email (SMTP preferred; SendGrid fallback)
EMAIL_TO      = (os.getenv("EMAIL_TO", "mukulsinghypm22@gmail.com")).strip()
EMAIL_FROM    = (os.getenv("EMAIL_FROM") or EMAIL_TO.split(",")[0]).strip()
SMTP_USER     = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS     = os.getenv("SMTP_PASS")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")  # optional fallback

# Telegram
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# HTTP
TIMEOUT = (15, 60)
HEADERS = {
    "User-Agent": os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

def _session():
    s = requests.Session()
    retry = Retry(total=6, connect=4, read=4, backoff_factor=2, status_forcelist=[429,500,502,503,504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    return s
session = _session()

def http_get(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    kw.setdefault("headers", HEADERS)
    return session.get(url, **kw)

def http_post(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    return session.post(url, **kw)

# =============== STATE ===============
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("[state] load error:", e)
    return {"qty": None, "in_stock": None}

def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    except Exception as e:
        print("[state] save error:", e)

# =============== NOTIFY ===============
def _email_subject(title, in_stock):
    if "Out of Stock" in title or in_stock is False: return f"🔴 {title}!"
    if "Back in Stock" in title or in_stock is True: return f"🟢 {title}!"
    if "Quantity" in title: return f"🔔 {title}!"
    return title

def send_email(subj, body):
    recipients = [x.strip() for x in EMAIL_TO.split(",") if x.strip()]
    if not recipients:
        print("[email] no recipients; skipping"); return

    # Prefer SMTP (Gmail App Password)
    if SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subj
            msg["From"] = EMAIL_FROM
            msg["To"] = ", ".join(recipients)
            ctx = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(EMAIL_FROM, recipients, msg.as_string())
            print(f"[email] sent via SMTP → {recipients}")
            return
        except Exception as e:
            print("[email] smtp error:", e)

    # Fallback: SendGrid
    if SENDGRID_API_KEY:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recipients]}],
                "from": {"email": EMAIL_FROM},  # must be verified on SendGrid
                "subject": subj,
                "content": [{"type": "text/plain", "value": body}],
            }
            r = http_post("https://api.sendgrid.com/v3/mail/send",
                          headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
                          json=payload)
            print("[email] sendgrid status:", r.status_code)
            return
        except Exception as e:
            print("[email] sendgrid error:", e)

    print("[email] no working transport; skipped")

def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[tg] not configured; skipping"); return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = http_post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print("[tg] status:", r.status_code)
    except Exception as e:
        print("[tg] failed:", e)

def notify(title, old_qty, new_qty, in_stock):
    body = (
        f"{title}\n\n"
        f"URL: {PRODUCT_URL}\n"
        f"Quantity: {old_qty} → {new_qty}\n"
        f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
    )
    send_email(_email_subject(title, in_stock), body)
    send_telegram(body)

# =============== PARSERS ===============
HURRY_PATTERNS = [
    re.compile(r"(?i)hurry[^0-9]{0,40}(\d{1,3}(?:,\d{3})*)\s*(left|remain(?:ing)?)"),
    re.compile(r"(?i)only[^0-9]{0,20}(\d{1,3}(?:,\d{3})*)\s*left"),
]
SOLD_PATTERNS = [
    re.compile(r"(?i)\bsold\s*out\b"),
    re.compile(r"(?i)\bout\s*of\s*stock\b"),
    re.compile(r"(?i)\bcurrently\s*unavailable\b"),
]

def extract_shopify_handle(url: str):
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    return base, (m.group(1) if m else None)

def product_variants(url: str):
    base, handle = extract_shopify_handle(url)
    if not handle: return base, []
    r = http_get(f"{base}/products/{handle}.js")
    r.raise_for_status()
    j = r.json()
    return base, j.get("variants") or []

def try_variant_json(url: str):
    try:
        base, variants = product_variants(url)
        if not variants: return None, None, None
        v = next((x for x in variants if x.get("available")), variants[0])
        vid = v["id"]
        # variant.json: sometimes includes inventory_quantity
        vres = http_get(f"{base}/variants/{vid}.json")
        qty, available = None, bool(v.get("available"))
        if vres.status_code == 200:
            vj = vres.json().get("variant", {})
            qty = vj.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0: qty = 0
            available = bool(vj.get("available", available))
        return vid, qty, available
    except Exception as e:
        print("[variant-json] error:", e)
        return None, None, None

def parse_html_fallback(html: str):
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.S|re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()

    for pat in HURRY_PATTERNS:
        m = pat.search(s)
        if m:
            try:
                q = int(m.group(1).replace(",", ""))
                return q, (q > 0)
            except Exception:
                pass

    if any(p.search(s) for p in SOLD_PATTERNS):
        return 0, False

    if "add to cart" in s.lower() or "in stock" in s.lower():
        return None, True

    return None, None

def get_quantity_and_stock(url: str):
    # 1) JSON route
    vid, qty, available = try_variant_json(url)
    if qty is not None or available is not None:
        print(f"[route:variant.json] qty={qty} available={available}")
        return qty, bool(available if available is not None else (qty and qty > 0))

    # 2) HTML fallback
    print("[route:html] fallback…")
    r = http_get(url, allow_redirects=True)
    r.raise_for_status()
    return parse_html_fallback(r.text)

# =============== MONITOR LOOP ===============
def main():
    print("=== Paaie product monitor started ===")
    print("URL:", PRODUCT_URL)
    st = load_state()
    prev_qty   = st.get("qty")
    prev_stock = st.get("in_stock")

    # first snapshot (optional)
    if FIRST_NOTIFY:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            notify("Initial observation", prev_qty, qty, bool(in_stock))
            prev_qty, prev_stock = qty, in_stock
            save_state({"qty": prev_qty, "in_stock": prev_stock})
        except Exception as e:
            print("[init] error:", e)

    while True:
        try:
            qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
            print(f"[now] qty={qty} in_stock={in_stock} | last qty={prev_qty} last stock={prev_stock}")

            changed = False
            title = None

            # Robust out-of-stock detection (qty==0 OR explicit sold-out)
            qty_zero_now = (qty == 0) or (in_stock is False)

            if qty_zero_now and prev_stock != False:
                changed = True
                title = "Product Out of Stock"

            elif (in_stock is True and prev_stock != True):
                changed = True
                title = "Product Back in Stock"

            elif (qty is not None and qty != prev_qty):
                changed = True
                title = "Quantity Updated" if prev_qty is not None else "Quantity Observed"

            if changed and title:
                notify(title, prev_qty, qty, bool(in_stock))
                prev_qty, prev_stock = qty, in_stock
                save_state({"qty": prev_qty, "in_stock": prev_stock})
            else:
                print("[no-change] no notification")

        except requests.exceptions.RequestException as e:
            print("[network] error:", e)  # transient issues → continue
        except Exception as e:
            print("[loop] error:", e)

        time.sleep(POLL_SECONDS + random.uniform(-3, 3))

if __name__ == "__main__":
    main()
