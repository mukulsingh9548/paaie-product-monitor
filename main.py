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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, requests
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================== CONFIG (from ENV) ==================
PRODUCT_URL = os.getenv("PRODUCT_URL", "").strip() or \
              "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing"

POLL_SECONDS   = max(10, int(os.getenv("POLL_SECONDS", "60")))
STATE_FILE     = os.getenv("STATE_FILE", "./paaie_state.json")
FIRST_NOTIFY   = os.getenv("FIRST_NOTIFY", "0") == "1"

EMAIL_TO       = os.getenv("EMAIL_TO", "mukulsinghmtr@gmail.com").strip()
EMAIL_FROM     = os.getenv("EMAIL_FROM", "mukulsinghypm22@gmail.com").strip()  # MUST be SendGrid verified
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TIMEOUT = (15, 60)

HEADERS = {
    "User-Agent": os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"),
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

# ================== HTTP session with retries ==================
def make_session():
    s = requests.Session()
    r = Retry(total=6, connect=4, read=4, backoff_factor=2.0,
              status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.mount("http://",  HTTPAdapter(max_retries=r))
    return s

S = make_session()

# ================== Notifications ==================
def send_email(subject: str, body: str):
    if not SENDGRID_API_KEY:
        print("🚫 SENDGRID_API_KEY missing → email skipped"); return
    try:
        resp = S.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": EMAIL_TO}]}],
                "from": {"email": EMAIL_FROM},  # must be verified sender in SendGrid
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            },
            timeout=20,
        )
        print(f"📨 SendGrid status: {resp.status_code}")
        if resp.status_code == 403:
            print("❌ SendGrid: From address not verified. Verify EMAIL_FROM in SendGrid.")
    except Exception as e:
        print("❌ Email failed:", e)

def send_telegram(text: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("⚠️ Telegram not configured; skip"); return
    try:
        r = S.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=12,
        )
        print("📲 Telegram status:", r.status_code)
    except Exception as e:
        print("❌ Telegram failed:", e)

def notify(title: str, qty, in_stock: bool):
    body = (
        f"{title}\n\n"
        f"URL: {PRODUCT_URL}\n"
        f"Quantity: {qty}\n"
        f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}"
    )
    send_email(title, body)
    send_telegram(body)

# ================== State ==================
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"last_seen_qty": None, "last_seen_stock": None,
            "last_notified_qty": None, "last_notified_stock": None}

def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)

# ================== Shopify helpers ==================
HURRY_PATS = [
    re.compile(r"(?i)\bhurry[^0-9]{0,40}(\d{1,3}(?:,\d{3})*)\s*(left|remain(?:ing)?)"),
    re.compile(r"(?i)\bonly[^0-9]{0,20}(\d{1,3}(?:,\d{3})*)\s*left"),
]
SOLD_PATS = [
    re.compile(r"(?i)\bsold\s*out\b"),
    re.compile(r"(?i)\bout\s*of\s*stock\b"),
    re.compile(r"(?i)\bcurrently\s*unavailable\b"),
]

def extract_base_handle(url: str):
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    return base, (m.group(1) if m else None)

def product_variants(url: str):
    base, handle = extract_base_handle(url)
    r = S.get(f"{base}/products/{handle}.js", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    return base, j.get("variants") or []

def choose_variant(url: str):
    try:
        base, variants = product_variants(url)
        if not variants: return base, None
        # prefer first available, else first
        v = next((x for x in variants if x.get("available")), variants[0])
        return base, int(v["id"])
    except Exception as e:
        print("⚠️ product JSON error:", e)
        base, _ = extract_base_handle(url)
        return base, None

def variant_json_qty(base: str, vid: int):
    try:
        v = S.get(f"{base}/variants/{vid}.json", headers=HEADERS, timeout=TIMEOUT)
        if v.status_code == 200:
            j = v.json().get("variant", {})
            qty = j.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0: qty = 0
            avail = bool(j.get("available", False))
            return qty, avail
    except Exception as e:
        print("⚠️ variant.json error:", e)
    return None, None

def cart_probe_qty(base: str, product_url: str, vid: int):
    """Return (qty, in_stock) via AJAX cart ceiling trick."""
    try:
        ajax = dict(AJAX_HEADERS); ajax["Origin"]=base; ajax["Referer"]=product_url
        S.post(f"{base}/cart/clear.js", headers=ajax, timeout=TIMEOUT)
        # add 1 then push to 999 to see max allowed
        add = S.post(f"{base}/cart/add.js", headers=ajax, data={"id": str(vid), "quantity": "1"}, timeout=TIMEOUT)
        if add.status_code >= 400:
            return None, None
        S.post(f"{base}/cart/change.js", headers=ajax, data={"id": str(vid), "quantity": "999"}, timeout=TIMEOUT)
        cart = S.get(f"{base}/cart.js", headers=ajax, timeout=TIMEOUT).json()
        S.post(f"{base}/cart/clear.js", headers=ajax, timeout=TIMEOUT)
        for it in cart.get("items", []):
            if str(it.get("variant_id") or it.get("id")) == str(vid):
                q = int(it.get("quantity", 0))
                if q >= 999:  # backorder/unlimited
                    return None, True
                return q, (q > 0)
    except Exception as e:
        print("⚠️ cart probe error:", e)
    return None, None

def html_fallback(url: str):
    try:
        h = S.get(url, headers=HEADERS, timeout=TIMEOUT).text
        s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", h, flags=re.S|re.I)
        s = re.sub(r"<[^>]+>", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        for pat in HURRY_PATS:
            m = pat.search(s)
            if m:
                q = int(m.group(1).replace(",", ""))
                return q, q > 0
        if any(p.search(s) for p in SOLD_PATS):
            return 0, False
        if "add to cart" in s.lower() or "in stock" in s.lower():
            return None, True
    except Exception as e:
        print("⚠️ html fallback error:", e)
    return None, None

def get_qty_and_stock(url: str):
    base, vid = choose_variant(url)
    # A) variants/{id}.json
    if vid:
        qty, avail = variant_json_qty(base, vid)
        if qty is not None or avail is not None:
            return qty, bool(avail if avail is not None else (qty and qty > 0))
        # B) cart probe
        q2, s2 = cart_probe_qty(base, url, vid)
        if q2 is not None or s2 is not None:
            return q2, bool(s2)
    # C) HTML
    return html_fallback(url)

# ================== MAIN LOOP (one-notification-per-change) ==================
def main():
    print("🚀 Paaie Product Monitor started")
    print("🔗", PRODUCT_URL)
    st = load_state()
    last_seen_qty    = st.get("last_seen_qty")
    last_seen_stock  = st.get("last_seen_stock")
    last_not_qty     = st.get("last_notified_qty")
    last_not_stock   = st.get("last_notified_stock")

    # Initial snapshot (optional)
    if FIRST_NOTIFY:
        try:
            q, s = get_qty_and_stock(PRODUCT_URL)
            notify("Initial observation", q, bool(s))
            last_seen_qty, last_seen_stock = q, s
            last_not_qty, last_not_stock = q, s
            save_state({
                "last_seen_qty": last_seen_qty, "last_seen_stock": last_seen_stock,
                "last_notified_qty": last_not_qty, "last_notified_stock": last_not_stock
            })
        except Exception as e:
            print("[init] error:", e)

    while True:
        try:
            qty, in_stock = get_qty_and_stock(PRODUCT_URL)
            print(f"📊 Now qty={qty} | stock={in_stock} | last_seen={last_seen_qty}/{last_seen_stock} | last_notified={last_not_qty}/{last_not_stock}")

            # Update seen
            last_seen_qty, last_seen_stock = qty, in_stock

            # Decide change (one-shot)
            title = None
            if (qty == 0) or (in_stock is False):
                # Out of stock
                if last_not_stock is not False or (last_not_qty not in (0, None)):
                    title = "Product Out of Stock"
            elif (in_stock is True) and (last_not_stock is not True):
                # Back in stock
                title = "Product Back in Stock"
            elif isinstance(qty, int) and (qty != last_not_qty):
                # Quantity changed (Hurry X left changed)
                title = "Quantity Updated"

            if title:
                notify(title, qty, bool(in_stock))
                last_not_qty, last_not_stock = qty, in_stock
                save_state({
                    "last_seen_qty": last_seen_qty, "last_seen_stock": last_seen_stock,
                    "last_notified_qty": last_not_qty, "last_notified_stock": last_not_stock
                })
            else:
                print("⏳ No change detected.")
        except Exception as e:
            print("❌ loop error:", e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
