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

import os
import re
import time
import json
import smtplib
import requests
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

# ========= USER CONFIG =========
PRODUCT_URL = "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing"

EMAIL_TO   = os.getenv("EMAIL_TO", "mukulsinghypm22@gmail.com").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "mukulsinghypm22@gmail.com").strip()

# NEW: SendGrid key (primary)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()

# SMTP (fallback)
SMTP_USER  = os.getenv("SMTP_USER", EMAIL_FROM)
SMTP_PASS  = (os.getenv("SMTP_PASS", "vhfznowpxhjkpsnj") or "").strip()  # Gmail App Password (16 chars)

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "8333104134:AAFGZ-0RoSMCded4h0tPRu7NvwWQuZPOams").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5042966410").strip()

CHECK_INTERVAL = 60          # seconds (production: 1800 = 30 min)
STATE_FILE     = "paaie_state.json"
TIMEOUT        = (15, 60)

# ========= HTTP =========
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
AJAX_HEADERS = {
    **HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

def make_session():
    s = requests.Session()
    retry = Retry(
        total=5, connect=3, read=3, backoff_factor=1.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter); s.mount("http://", adapter)
    return s

SESSION = make_session()

# ========= EMAIL (SendGrid primary, SMTP fallback) =========
def send_email(subject: str, body: str) -> None:
    recipients = [r.strip() for r in EMAIL_TO.split(",") if r.strip()]

    # 1) SendGrid (recommended on Render)
    if SENDGRID_API_KEY and recipients:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recipients]}],
                "from": {"email": EMAIL_FROM},   # MUST be a verified Single Sender/Domain in SendGrid
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            r = SESSION.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
            print(f"[email] sendgrid status: {r.status_code}")
            if 200 <= r.status_code < 300:
                return
            else:
                print(f"[email] sendgrid non-2xx: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print("[email] sendgrid error:", e)

    # 2) SMTP fallback (Gmail App Password)
    if not (SMTP_USER and SMTP_PASS and len(SMTP_PASS) >= 16 and recipients):
        print("[email] smtp not usable; skipping")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(recipients)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        print(f"[email] sent via SMTP → {recipients}")
    except Exception as e:
        print("❌ Email send failed (SMTP):", e)

# ========= TELEGRAM =========
def send_telegram(message: str) -> None:
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            print("⚠️ Telegram credentials missing. Skipping Telegram notification.")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"📲 Telegram sent → {message.splitlines()[0]}")
        else:
            print("⚠️ Telegram send failed:", resp.text)
    except Exception as e:
        print("❌ Telegram error:", e)

# ========= STATE =========
def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)

# ========= URL / PREFIX =========
def extract_shopify_handle_and_prefix(product_url: str) -> tuple[str, str, str]:
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    path = u.path.strip("/")
    parts = path.split("/")

    prefix = ""
    handle = None

    if len(parts) >= 3 and parts[1] == "products":
        prefix = "/" + parts[0]
        handle = parts[2]
    elif len(parts) >= 2 and parts[0] == "products":
        handle = parts[1]
    else:
        m = re.search(r"/products/([^/?#]+)", u.path)
        if m:
            handle = m.group(1)

    if not handle:
        raise ValueError("Product handle not found in URL")

    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    if "products" in prefix:
        prefix = ""

    return base, prefix, handle

def choose_variant_id(product_url: str) -> tuple[str, str, int | None, bool]:
    base, prefix, handle = extract_shopify_handle_and_prefix(product_url)
    try:
        r = SESSION.get(f"{base}{prefix}/products/{handle}.js", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        p = r.json()
        variants = p.get("variants", []) or []
        if not variants:
            return base, prefix, None, False
        v = next((v for v in variants if v.get("available")), variants[0])
        any_available = any(v.get("available") for v in variants)
        return base, prefix, int(v["id"]), any_available
    except Exception as e:
        print("⚠️ product JSON error:", e)
        return base, prefix, None, False

# ========= AJAX CART PROBE =========
def get_quantity_via_cart_probe(base: str, prefix: str, variant_id: int):
    try:
        SESSION.post(f"{base}{prefix}/cart/clear.js", headers=AJAX_HEADERS, timeout=TIMEOUT)
        add_res = SESSION.post(
            f"{base}{prefix}/cart/add.js",
            headers=AJAX_HEADERS,
            data={"id": str(variant_id), "quantity": 1},
            timeout=TIMEOUT,
        )
        if add_res.status_code >= 400:
            return 0, False, False

        cart_res = SESSION.get(f"{base}{prefix}/cart.js", headers=AJAX_HEADERS, timeout=TIMEOUT)
        cart = cart_res.json() if cart_res.status_code == 200 else {}
        items = cart.get("items", []) if isinstance(cart, dict) else []
        line = next((it for it in items if str(it.get("id")) == str(variant_id)), None)
        if not line:
            return 0, False, False

        line_key = line.get("key")
        SESSION.post(
            f"{base}{prefix}/cart/change.js",
            headers=AJAX_HEADERS,
            data={"id": line_key, "quantity": 999},
            timeout=TIMEOUT,
        )
        final_cart_res = SESSION.get(f"{base}{prefix}/cart.js", headers=AJAX_HEADERS, timeout=TIMEOUT)
        final_cart = final_cart_res.json() if final_cart_res.status_code == 200 else {}
        items = final_cart.get("items", []) if isinstance(final_cart, dict) else []
        line = next((it for it in items if str(it.get("id")) == str(variant_id)), None)
        if not line:
            return 0, False, False

        qty = int(line.get("quantity", 0))
        in_stock = qty > 0
        backorder_mode = qty >= 999
        if backorder_mode:
            return None, True, True
        return qty, in_stock, False
    except Exception as e:
        print("❌ cart probe error:", e)
    return None, False, False

# ========= FALLBACK VARIANT =========
def get_quantity_via_variant_json(base: str, prefix: str, variant_id: int):
    try:
        v = SESSION.get(f"{base}{prefix}/variants/{variant_id}.json", headers=HEADERS, timeout=TIMEOUT)
        if v.status_code == 200:
            vj = v.json().get("variant", {})
            qty2 = vj.get("inventory_quantity")
            avail2 = bool(vj.get("available", False))
            return qty2, avail2
    except Exception as e:
        print("⚠️ variants JSON error:", e)
    return None, False

# ========= GET QUANTITY ENTRY =========
def get_quantity_from_shopify(product_url: str):
    base, prefix, variant_id, any_available = choose_variant_id(product_url)
    if variant_id is None:
        return None, False

    qty, in_stock, backorder = get_quantity_via_cart_probe(base, prefix, variant_id)
    if qty is not None or in_stock or backorder:
        return qty, in_stock

    qty2, avail2 = get_quantity_via_variant_json(base, prefix, variant_id)
    if qty2 is not None or avail2:
        return qty2, avail2

    # HTML fallback optional (your original didn’t have; keeping code unchanged as you asked)
    return None, any_available

# ========= MAIN LOOP =========
def main():
    print("🚀 Paaie Product Monitor started…")
    print(f"🔗 URL: {PRODUCT_URL}")

    while True:
        try:
            qty, in_stock = get_quantity_from_shopify(PRODUCT_URL)
            state = load_state()

            last_seen_qty   = state.get("last_seen_qty")
            last_notified_q = state.get("last_notified_qty_change")

            print(f"📊 Qty now: {qty} | Seen: {last_seen_qty} | Notified: {last_notified_q} | In stock: {in_stock}")

            if isinstance(qty, int):
                if last_seen_qty is None and last_notified_q is None:
                    state["last_seen_qty"] = qty
                    state["qty"] = qty
                else:
                    if qty != last_notified_q:
                        prev_txt = "unknown" if last_seen_qty is None else str(last_seen_qty)
                        msg = f"Quantity updated: {prev_txt} → {qty}\n{PRODUCT_URL}"
                        send_email("🔔 Quantity Updated!", msg)
                        send_telegram(f"🔔 Quantity Updated!\n{msg}")

                        if qty > 0:
                            send_email("🟢 Product Back in Stock!", f"Current quantity: {qty}\n{PRODUCT_URL}")
                            send_telegram(f"🟢 Product Back in Stock!\nCurrent quantity: {qty}\n{PRODUCT_URL}")
                        else:
                            send_email("🔴 Product Out of Stock!", f"Current quantity: 0\n{PRODUCT_URL}")
                            send_telegram(f"🔴 Product Out of Stock!\nCurrent quantity: 0\n{PRODUCT_URL}")

                        state["last_notified_qty_change"] = qty

                    state["last_seen_qty"] = qty
                    state["qty"] = qty

            state["in_stock"] = bool(in_stock)
            save_state(state)

        except Exception as e:
            print("❌ Error:", e)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

