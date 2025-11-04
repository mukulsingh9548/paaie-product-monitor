# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-

# import os, re, time, json, smtplib, ssl, random, sys, requests
# from email.mime.text import MIMEText
# from urllib.parse import urlparse
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry

# # =============== CONFIG ===============
# PRODUCT_URL   = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
# CHECK_SECONDS = max(10, int(os.getenv("POLL_SECONDS", "120")))
# STATE_FILE    = os.getenv("STATE_FILE", "./product_state.json")
# FIRST_NOTIFY  = os.getenv("FIRST_NOTIFY", "1") == "1"     # first boot par 1 notification

# EMAIL_TO   = os.getenv("EMAIL_TO", "").strip()
# EMAIL_FROM = (os.getenv("EMAIL_FROM") or EMAIL_TO.split(",")[0] or "").strip()
# SMTP_USER  = os.getenv("SMTP_USER") or EMAIL_FROM
# SMTP_PASS  = os.getenv("SMTP_PASS")
# SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
# SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))

# SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

# TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
# TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# TIMEOUT = (15, 60)

# # =============== HEADERS ===============
# HEADERS = {
#     "User-Agent": os.getenv(
#         "USER_AGENT",
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
#     ),
#     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#     "Accept-Language": "en-US,en;q=0.9",
#     "Cache-Control": "no-cache",
# }

# AJAX_HEADERS = {
#     **HEADERS,
#     "X-Requested-With": "XMLHttpRequest",
#     "Accept": "application/json, text/javascript, */*; q=0.01",
#     "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
# }

# # =============== HTTP SESSION ===============
# def make_session():
#     s = requests.Session()
#     retry = Retry(total=7, connect=4, read=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
#     adapter = HTTPAdapter(max_retries=retry)
#     s.mount("https://", adapter)
#     s.mount("http://", adapter)
#     return s

# session = make_session()

# def http_get(url, **kwargs):
#     kwargs.setdefault("timeout", TIMEOUT)
#     return session.get(url, **kwargs)

# def http_post(url, **kwargs):
#     kwargs.setdefault("timeout", TIMEOUT)
#     return session.post(url, **kwargs)

# # =============== STATE ===============
# def load_state():
#     try:
#         if os.path.exists(STATE_FILE):
#             with open(STATE_FILE, "r", encoding="utf-8") as f:
#                 return json.load(f)
#     except Exception as e:
#         print("[state] load error:", e)
#     return {"qty": None, "in_stock": None}

# def save_state(state):
#     try:
#         with open(STATE_FILE, "w", encoding="utf-8") as f:
#             json.dump(state, f, indent=2)
#     except Exception as e:
#         print("[state] save error:", e)

# # =============== NOTIFIERS ===============
# def send_email(subject, body):
#     recipients = [r.strip() for r in EMAIL_TO.split(",") if r.strip()]
#     if not recipients:
#         print("[email] no recipients configured; skipping")
#         return

#     # SendGrid HTTP (preferred)
#     if SENDGRID_API_KEY:
#         try:
#             payload = {
#                 "personalizations": [{"to": [{"email": e} for e in recipients]}],
#                 "from": {"email": EMAIL_FROM},   # must be verified Single Sender
#                 "subject": subject,
#                 "content": [{"type": "text/plain", "value": body}],
#             }
#             r = http_post(
#                 "https://api.sendgrid.com/v3/mail/send",
#                 headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
#                 json=payload,
#             )
#             print(f"[email] sendgrid status: {r.status_code}")
#             if 200 <= r.status_code < 300:
#                 return
#             else:
#                 print(f"[email] sendgrid non-2xx: {r.status_code} {r.text[:200]}")
#         except Exception as e:
#             print("[email] sendgrid error:", e)

#     # SMTP fallback
#     if not (SMTP_USER and SMTP_PASS):
#         print("[email] smtp not configured; skipping")
#         return
#     msg = MIMEText(body, "plain", "utf-8")
#     msg["Subject"] = subject
#     msg["From"]    = EMAIL_FROM
#     msg["To"]      = ", ".join(recipients)
#     ctx = ssl.create_default_context()
#     with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
#         s.starttls(context=ctx)
#         s.login(SMTP_USER, SMTP_PASS)
#         s.sendmail(msg["From"], recipients, msg.as_string())
#     print(f"[email] sent via SMTP → {recipients}")

# def send_telegram(text):
#     if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
#         print("[tg] not configured; skipping")
#         return
#     try:
#         url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
#         r = http_post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
#         print("[tg] status:", r.status_code)
#     except Exception as e:
#         print("[tg] failed:", e)

# def notify(title, old_qty, new_qty, in_stock):
#     body = (
#         f"{title}\n\n"
#         f"URL: {PRODUCT_URL}\n"
#         f"Quantity: {old_qty} → {new_qty}\n"
#         f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
#     )
#     send_email(f"[Paaie] {title}", body)
#     send_telegram(body)

# # =============== PARSERS ===============
# HURRY_PATTERNS = [
#     re.compile(r"\bHurry[^0-9]{0,20}(\d+)\s*(?:left|remain)", re.I),
#     re.compile(r"\bOnly\s*(\d+)\s*left\b", re.I),
# ]

# def extract_shopify_handle(product_url: str):
#     u = urlparse(product_url)
#     base = f"{u.scheme}://{u.netloc}"
#     m = re.search(r"/products/([^/?#]+)", u.path)
#     return base, (m.group(1) if m else None)

# def product_and_variants(product_url: str):
#     base, handle = extract_shopify_handle(product_url)
#     if not handle:
#         return base, None
#     p = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
#     p.raise_for_status()
#     return base, p.json().get("variants") or []

# def try_variant_json(product_url: str):
#     try:
#         base, variants = product_and_variants(product_url)
#         if not variants:
#             return None, None, None
#         v = next((v for v in variants if v.get("available")), variants[0])
#         vid = v["id"]
#         vres = http_get(f"{base}/variants/{vid}.json", headers=HEADERS)
#         qty, available = None, bool(v.get("available"))
#         if vres.status_code == 200:
#             vj = vres.json().get("variant", {})
#             qty = vj.get("inventory_quantity")
#             if isinstance(qty, int) and qty < 0:
#                 qty = 0
#             available = bool(vj.get("available", available))
#         return vid, qty, available
#     except Exception as e:
#         print("[variant-json] error:", e)
#         return None, None, None

# def cart_probe_qty(product_url: str, variant_id: int):
#     try:
#         base, _ = extract_shopify_handle(product_url)
#         ajax = dict(AJAX_HEADERS)
#         ajax["Origin"]  = base
#         ajax["Referer"] = product_url
#         # Clear → Add huge qty → Read → Clear
#         http_post(f"{base}/cart/clear.js", headers=ajax)
#         http_post(f"{base}/cart/add.js", headers=ajax, data={"id": str(variant_id), "quantity": "999"})
#         cart = http_get(f"{base}/cart.js", headers=ajax)
#         cart.raise_for_status()
#         data = cart.json()
#         for item in data.get("items", []):
#             if str(item.get("variant_id")) == str(variant_id):
#                 qty = int(item.get("quantity") or 0)
#                 http_post(f"{base}/cart/clear.js", headers=ajax)
#                 return qty
#         http_post(f"{base}/cart/clear.js", headers=ajax)
#     except Exception as e:
#         print("[cart-probe] error:", e)
#     return None

# def parse_html_hurry(html: str):
#     text = re.sub(r"<[^>]+>", " ", html)
#     text = re.sub(r"\s+", " ", text)
#     for pat in HURRY_PATTERNS:
#         m = pat.search(text)
#         if m:
#             try:
#                 return int(m.group(1))
#             except Exception:
#                 pass
#     # stock hint
#     in_stock = "in stock" in text.lower()
#     return None, in_stock

# def get_quantity_and_stock(product_url: str):
#     # 1) variant.json
#     vid, qty, available = try_variant_json(product_url)
#     if qty is not None or available is not None:
#         print(f"[route:variant.json] qty={qty} available={available}")
#         # If qty unknown but available → 2) cart probe
#         if qty is None and available and vid:
#             q2 = cart_probe_qty(product_url, vid)
#             if isinstance(q2, int):
#                 qty = q2
#         return qty, bool(available if available is not None else (qty and qty > 0))

#     # 2) cart probe (no json)
#     if vid:
#         q2 = cart_probe_qty(product_url, vid)
#         if isinstance(q2, int):
#             return q2, q2 > 0

#     # 3) HTML fallback for “Hurry, Only X left!”
#     print("[route:html] fallback…")
#     r = http_get(product_url, headers=HEADERS, allow_redirects=True)
#     r.raise_for_status()
#     h = r.text
#     for pat in HURRY_PATTERNS:
#         m = pat.search(h)
#         if m:
#             try:
#                 q = int(m.group(1))
#                 return q, q > 0
#             except Exception:
#                 pass
#     # last resort: simple in-stock hint
#     return None, ("in stock" in h.lower())

# # =============== MONITOR LOOP ===============
# def main():
#     print("=== Paaie product monitor started ===")
#     print("URL:", PRODUCT_URL)
#     st = load_state()
#     prev_qty   = st.get("qty")
#     prev_stock = st.get("in_stock")

#     # bootstrap notification once (if configured)
#     if FIRST_NOTIFY:
#         try:
#             qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
#             notify("Initial observation", prev_qty, qty, bool(in_stock))
#             prev_qty, prev_stock = qty, in_stock
#             save_state({"qty": prev_qty, "in_stock": prev_stock})
#         except Exception as e:
#             print("[init] error:", e)

#     # loop
#     while True:
#         try:
#             qty, in_stock = get_quantity_and_stock(PRODUCT_URL)
#             print(f"[now] qty={qty} in_stock={in_stock} | last qty={prev_qty} last stock={prev_stock}")

#             changed = False
#             title = None

#             # Stock flip?
#             if (in_stock is not None and prev_stock is not None) and (in_stock != prev_stock):
#                 changed = True
#                 title = "Product Back in Stock" if in_stock else "Product Out of Stock"

#             # Quantity change?
#             if qty is not None and qty != prev_qty:
#                 changed = True
#                 if qty == 0:
#                     title = "Product Out of Stock"
#                 elif prev_qty is None:
#                     title = title or "Quantity Observed"
#                 else:
#                     title = title or "Quantity Updated"

#             if changed:
#                 notify(title, prev_qty, qty, bool(in_stock))
#                 prev_qty, prev_stock = qty, in_stock
#                 save_state({"qty": prev_qty, "in_stock": prev_stock})
#             else:
#                 print("[no-change] no notification")

#         except requests.exceptions.RequestException as e:
#             print("[network] error:", e)
#         except Exception as e:
#             print("[loop] error:", e)

#         time.sleep(CHECK_SECONDS + random.uniform(-3, 3))


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========= .env =========
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ========= CONFIG =========
PRODUCT_URL = "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing"

EMAIL_TO   = os.getenv("EMAIL_TO", "mukulsinghmtr@gmail.com")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_TO)
SMTP_USER  = os.getenv("SMTP_USER", EMAIL_FROM)
SMTP_PASS  = (os.getenv("SMTP_PASS", "") or "").replace(" ", "")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")  # fallback
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

STATE_FILE = "paaie_state.json"
CHECK_INTERVAL = 90
TIMEOUT = (15, 60)

# ========= SESSION =========
def make_session():
    s = requests.Session()
    retry = Retry(total=5, connect=3, read=3, backoff_factor=1.6,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s
SESSION = make_session()

# ========= EMAIL =========
def send_email(subject: str, body: str):
    """Try Gmail SMTP → fallback SendGrid API"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    recipients = [EMAIL_TO]

    # 1️⃣ Try SMTP
    try:
        print("📧 Trying Gmail SMTP...")
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as s:
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, recipients, msg.as_string())
        print(f"✅ Email sent via SMTP → {EMAIL_TO}")
        return
    except Exception as e:
        print(f"⚠️ SMTP failed: {e}")

    # 2️⃣ Try SendGrid fallback
    if SENDGRID_API_KEY:
        try:
            r = SESSION.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": EMAIL_TO}]}],
                    "from": {"email": EMAIL_FROM},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=15,
            )
            print(f"📨 SendGrid status: {r.status_code}")
            if 200 <= r.status_code < 300:
                print(f"✅ Email sent via SendGrid → {EMAIL_TO}")
                return
            else:
                print("❌ SendGrid error:", r.text[:200])
        except Exception as e:
            print("❌ SendGrid fallback failed:", e)

    print("🚫 Email could not be sent by any method")

# ========= TELEGRAM =========
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram creds missing; skip.")
        return
    try:
        r = SESSION.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
        print(f"📲 Telegram status: {r.status_code}")
    except Exception as e:
        print("❌ Telegram send failed:", e)

# ========= STATE =========
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {}

def save_state(data):
    json.dump(data, open(STATE_FILE, "w"), indent=2)

# ========= PARSING =========
def extract_shopify_handle(product_url):
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    handle = m.group(1) if m else None
    return base, handle

def get_variant(product_url):
    base, handle = extract_shopify_handle(product_url)
    r = SESSION.get(f"{base}/products/{handle}.js", timeout=TIMEOUT)
    if r.status_code != 200:
        raise Exception(f"product JSON error: {r.status_code}")
    data = r.json()
    v = next((x for x in data["variants"] if x["available"]), data["variants"][0])
    return base, v["id"], v.get("available")

def get_quantity(product_url):
    try:
        base, vid, available = get_variant(product_url)
        cart = SESSION.get(f"{base}/variants/{vid}.json", timeout=TIMEOUT)
        if cart.status_code == 200:
            variant = cart.json().get("variant", {})
            qty = variant.get("inventory_quantity", None)
            return qty, bool(variant.get("available", available))
    except Exception as e:
        print("⚠️ Quantity fetch failed:", e)
    return None, False

# ========= MAIN LOOP =========
def main():
    print("🚀 Paaie Product Monitor started...")
    print(f"🔗 URL: {PRODUCT_URL}")

    state = load_state()
    prev_qty = state.get("qty")
    prev_stock = state.get("in_stock")

    while True:
        try:
            qty, in_stock = get_quantity(PRODUCT_URL)
            print(f"📊 Now qty={qty} | stock={in_stock} | prev qty={prev_qty}")

            if qty != prev_qty or in_stock != prev_stock:
                if qty == 0 or not in_stock:
                    title = "🔴 Product Out of Stock!"
                elif prev_qty == 0 and qty > 0:
                    title = "🟢 Product Back in Stock!"
                else:
                    title = "🔔 Quantity Updated!"

                msg = f"{title}\nCurrent quantity: {qty}\n{PRODUCT_URL}"
                send_email(title, msg)
                send_telegram(msg)

                state = {"qty": qty, "in_stock": in_stock}
                save_state(state)
                prev_qty, prev_stock = qty, in_stock
            else:
                print("⏳ No change detected.")
        except Exception as e:
            print("❌ Loop error:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
