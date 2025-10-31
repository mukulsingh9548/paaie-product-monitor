# ==== QUANTITY WATCHER (scrape "Hurry, Only X left!") ====
import os, re, time, json, random, smtplib, ssl, requests
from email.mime.text import MIMEText
from threading import Thread

PRODUCT_URL = os.getenv("PRODUCT_URL", "https://www.paaie.com/products/24-kt-5-gram-fortuna-pamp-gold-bar-testing")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_TO  = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "")

STATE_FILE = os.getenv("STATE_FILE", "/data/scrape_state.json")

QTY_PATTERNS = [
    re.compile(r"Hurry[^0-9]{0,20}(\d+)\s*(?:left|remaining)", re.I),
    re.compile(r"Only\s*(\d+)\s*left", re.I),
    re.compile(r"\b(\d+)\s*left\b", re.I),
]

def _debug(msg): print(f"[QWATCH] {msg}", flush=True)

def _load_state():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        if os.path.exists(STATE_FILE):
            return json.load(open(STATE_FILE, "r", encoding="utf-8"))
    except Exception as e:
        _debug(f"state load error: {e!r}")
    return {"qty": None}

def _save_state(qty):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        json.dump({"qty": qty}, open(STATE_FILE, "w", encoding="utf-8"))
    except Exception as e:
        _debug(f"state save error: {e!r}")

def _send_email(subject, body):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_TO):
        _debug("email not configured; skip"); return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, (EMAIL_FROM or SMTP_USER), EMAIL_TO
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls(context=ctx); s.login(SMTP_USER, SMTP_PASS); s.sendmail(msg["From"], [EMAIL_TO], msg.as_string())

def _send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        _debug("telegram not configured; skip"); return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for _ in range(3):
        try:
            r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
            if r.status_code == 200: return
        except requests.RequestException: pass
        time.sleep(2)

def _notify(title, old_qty, new_qty):
    status = "IN STOCK ✅" if (new_qty or 0) > 0 else "OUT OF STOCK ⛔"
    body = "\n".join([title, f"URL: {PRODUCT_URL}", f"Quantity: {old_qty} → {new_qty}", f"Status: {status}"])
    _send_email(f"[Paaie] {title}", body); _send_telegram(body)

def _fetch_html():
    headers = {"User-Agent": USER_AGENT, "Cache-Control": "no-cache"}
    last_exc = None
    for a in range(1, 6):
        try:
            r = requests.get(PRODUCT_URL, headers=headers, timeout=15)
            if r.status_code == 200: return r.text
            _debug(f"HTTP {r.status_code}")
        except requests.RequestException as e:
            last_exc = e; _debug(f"net err: {e!r}")
        time.sleep(min(12, 2**a) + random.uniform(0, 0.8))
    raise RuntimeError(f"fetch failed: {last_exc!r}")

def _extract_qty(html: str):
    text = re.sub(r"<[^>]+>", " ", html); text = re.sub(r"\s+", " ", text)
    for pat in QTY_PATTERNS:
        m = pat.search(text)
        if m:
            try: return int(m.group(1))
            except Exception: pass
    return None

def _quantity_loop():
    _debug("started")
    st = _load_state(); prev = st.get("qty")
    _debug(f"initial qty: {prev}")
    FIRST_NOTIFY = os.getenv("FIRST_NOTIFY", "1") == "1"
    while True:
        try:
            qty = _extract_qty(_fetch_html())
            if qty is None: _debug("pattern not found")
            else:
                if prev is None and FIRST_NOTIFY:
                    _notify("Initial quantity observed", None, qty); _save_state(qty); prev = qty
                elif qty != prev:
                    title = "Product quantity updated" if qty > 0 else "Product is OUT OF STOCK"
                    _notify(title, prev, qty); _save_state(qty); prev = qty
                else: _debug("no change")
        except Exception as e:
            _debug(f"loop err: {e!r}")
        time.sleep(max(10, int(POLL_SECONDS) + random.uniform(-5, 5)))

def start_quantity_watcher():
    from threading import Thread
    Thread(target=_quantity_loop, daemon=True).start()
    _debug("thread launched")
# ==== END QUANTITY WATCHER ==============================================
