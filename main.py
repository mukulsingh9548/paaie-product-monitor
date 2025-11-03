#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, json, smtplib, ssl, random, threading, requests
from email.mime.text import MIMEText
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============== CONFIG ===============
PRODUCT_URL   = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
POLL_SECONDS  = max(20, int(os.getenv("POLL_SECONDS", "120")))
STATE_FILE    = os.getenv("STATE_FILE", "./product_state.json")
FIRST_NOTIFY  = os.getenv("FIRST_NOTIFY", "0") == "1"   # Render par duplicates avoid, default 0

EMAIL_TO   = (os.getenv("EMAIL_TO") or "").strip()
EMAIL_FROM = (os.getenv("EMAIL_FROM") or EMAIL_TO.split(",")[0] or "").strip()
SMTP_USER  = os.getenv("SMTP_USER") or EMAIL_FROM
SMTP_PASS  = os.getenv("SMTP_PASS")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")  # Single Sender verified hona chahiye

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEOUT = (15, 60)

# =============== HEADERS/SESSION ===============
HEADERS = {
    "User-Agent": os.getenv("USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

AJAX_HEADERS = {
    **HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

def make_session():
    s = requests.Session()
    retry = Retry(total=7, connect=4, read=4, backoff_factor=1.8,
                  status_forcelist=[429, 500, 502, 503, 504])
    ad = HTTPAdapter(max_retries=retry)
    s.mount("https://", ad); s.mount("http://", ad)
    return s
session = make_session()

def http_get(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    # cache-buster so “Hurry X left” ka stale page na aaye
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}_t={int(time.time())}"
    return session.get(url, **kw)

def http_post(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    return session.post(url, **kw)

# =============== STATE (dedupe) ===============
def _default_state():
    return {"qty": None, "in_stock": None}

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("[state] load error:", e)
    return _default_state()

def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    except Exception as e:
        print("[state] save error:", e)

# =============== NOTIFIERS ===============
def send_email(subject, body):
    recips = [r.strip() for r in (EMAIL_TO or "").split(",") if r.strip()]
    if not recips:
        print("[email] no recipients; skip")
        return

    # Prefer SendGrid
    if SENDGRID_API_KEY:
        try:
            payload = {
                "personalizations": [{"to": [{"email": e} for e in recips]}],
                "from": {"email": EMAIL_FROM},  # verified single sender
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }
            r = http_post("https://api.sendgrid.com/v3/mail/send",
                          headers={"Authorization": f"Bearer {SENDGRID_API_KEY}",
                                   "Content-Type": "application/json"},
                          json=payload)
            print("[email] sendgrid status:", r.status_code)
            if 200 <= r.status_code < 300:
                return
            else:
                print("[email] sendgrid resp:", r.text[:200])
        except Exception as e:
            print("[email] sendgrid err:", e)

    # SMTP fallback
    if not (SMTP_USER and SMTP_PASS):
        print("[email] no SMTP; skip")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject; msg["From"] = EMAIL_FROM; msg["To"] = ", ".join(recips)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ctx); s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(msg["From"], recips, msg.as_string())
    print("[email] sent via SMTP")

def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[tg] not configured; skip"); return
    try:
        r = http_post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print("[tg] status:", r.status_code)
    except Exception as e:
        print("[tg] err:", e)

def notify(title, old_qty, new_qty, in_stock):
    body = (f"{title}\n\nURL: {PRODUCT_URL}\n"
            f"Quantity: {old_qty} → {new_qty}\n"
            f"Status: {'IN STOCK ✅' if in_stock else 'OUT OF STOCK ⛔'}")
    send_email(f"[Paaie] {title}", body)
    send_telegram(body)

# =============== PARSERS ===============
HURRY_PATTERNS = [
    re.compile(r"\bHurry[^0-9]{0,30}(\d+)\s*(?:left|remain)", re.I),
    re.compile(r"\bOnly\s*(\d+)\s*left\b", re.I),
]

def extract_shopify_handle(u: str):
    from urllib.parse import urlparse
    pu = urlparse(u)
    base = f"{pu.scheme}://{pu.netloc}"
    m = re.search(r"/products/([^/?#]+)", pu.path)
    return base, (m.group(1) if m else None)

def product_and_variants(u: str):
    base, handle = extract_shopify_handle(u)
    if not handle: return base, []
    r = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
    r.raise_for_status()
    return base, (r.json().get("variants") or [])

def try_variant_json(u: str):
    try:
        base, variants = product_and_variants(u)
        if not variants: return None, None, None
        v = next((v for v in variants if v.get("available")), variants[0])
        vid = v["id"]
        r = http_get(f"{base}/variants/{vid}.json", headers=HEADERS)
        qty, available = None, bool(v.get("available"))
        if r.status_code == 200:
            vj = r.json().get("variant", {})
            qty = vj.get("inventory_quantity")
            if isinstance(qty, int) and qty < 0: qty = 0
            available = bool(vj.get("available", available))
        return vid, qty, available
    except Exception as e:
        print("[variant-json] err:", e)
        return None, None, None

def cart_probe_qty(u: str, variant_id: int):
    try:
        base, _ = extract_shopify_handle(u)
        ajax = dict(AJAX_HEADERS); ajax["Origin"] = base; ajax["Referer"] = u
        http_post(f"{base}/cart/clear.js", headers=ajax)
        http_post(f"{base}/cart/add.js", headers=ajax, data={"id": str(variant_id), "quantity": "999"})
        r = http_get(f"{base}/cart.js", headers=ajax); r.raise_for_status()
        for item in r.json().get("items", []):
            if str(item.get("variant_id")) == str(variant_id):
                q = int(item.get("quantity") or 0)
                http_post(f"{base}/cart/clear.js", headers=ajax)
                return q
        http_post(f"{base}/cart/clear.js", headers=ajax)
    except Exception as e:
        print("[cart-probe] err:", e)
    return None

def parse_hurry_html(html: str):
    # strip tags quickly to handle “Hurry, Only X left!”
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    for pat in HURRY_PATTERNS:
        m = pat.search(txt)
        if m:
            try:
                return int(m.group(1))
            except:  # noqa
                pass
    return None

def get_quantity_and_stock(u: str):
    # 1) variants json
    vid, qty, avail = try_variant_json(u)
    if qty is not None or avail is not None:
        if qty is None and avail and vid:
            q2 = cart_probe_qty(u, vid)
            if isinstance(q2, int): qty = q2
        return qty, bool(avail if avail is not None else (qty and qty > 0))

    # 2) cart probe if id known
    if vid:
        q2 = cart_probe_qty(u, vid)
        if isinstance(q2, int): return q2, q2 > 0

    # 3) html hurry
    r = http_get(u, headers=HEADERS, allow_redirects=True)
    r.raise_for_status()
    q = parse_hurry_html(r.text)
    if isinstance(q, int): return q, q > 0
    return None, ("in stock" in r.text.lower())

# =============== MONITOR LOOP ===============
_monitor_started = False

def _loop():
    print("=== Monitor started ===")
    st = load_state()
    prev_qty, prev_stock = st.get("qty"), st.get("in_stock")

    # Optional first snapshot
    if FIRST_NOTIFY:
        try:
            q, s = get_quantity_and_stock(PRODUCT_URL)
            notify("Initial observation", prev_qty, q, bool(s))
            prev_qty, prev_stock = q, s
            save_state({"qty": prev_qty, "in_stock": prev_stock})
        except Exception as e:
            print("[init] err:", e)

    while True:
        try:
            q, s = get_quantity_and_stock(PRODUCT_URL)
            print(f"[check] qty={q} stock={s} | last qty={prev_qty} stock={prev_stock}")

            changed = False
            title = None

            # Stock flip
            if (s is not None and prev_stock is not None) and (s != prev_stock):
                changed = True
                title = "Product Back in Stock" if s else "Product Out of Stock"

            # Quantity change
            if q is not None and q != prev_qty:
                changed = True
                if q == 0:
                    title = "Product Out of Stock"
                elif prev_qty is None:
                    title = title or "Quantity Observed"
                else:
                    title = title or "Quantity Updated"

            if changed:
                notify(title, prev_qty, q, bool(s))
                prev_qty, prev_stock = q, s
                save_state({"qty": prev_qty, "in_stock": prev_stock})
            else:
                print("[no-change] stable")
        except requests.exceptions.RequestException as e:
            print("[network] err:", e)
        except Exception as e:
            print("[loop] err:", e)

        time.sleep(POLL_SECONDS + random.uniform(-3, 3))

def start_monitor_if_needed():
    global _monitor_started
    if _monitor_started:
        return
    _monitor_started = True
    t = threading.Thread(target=_loop, name="paaie-monitor", daemon=True)
    t.start()
