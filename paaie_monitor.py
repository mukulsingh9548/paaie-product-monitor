import os, re, time, json, smtplib
import requests
from email.mime.text import MIMEText
from urllib.parse import urlparse

# ===================== USER CONFIG =====================
PRODUCT_URL = "https://www.paaie.com/products/1-gram-fortuna-pamp-gold-bar?_pos=2&_sid=34ee79695&_ss=r"

EMAIL_TO   = "mukulsinghypm22@gmail.com"
EMAIL_FROM = "mukulsinghypm22@gmail.com"
SMTP_USER  = "mukulsinghypm22@gmail.com"
SMTP_PASS  = os.getenv("SMTP_PASS", "PUT_YOUR_16_CHAR_APP_PASSWORD_HERE")  # <-- App Password (16 chars)

CHECK_INTERVAL = 60          # seconds (testing)
STATE_FILE     = "paaie_state.json"
TIMEOUT        = (15, 60)    # (connect, read)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ===================== HELPERS =====================
def send_email(subject: str, body: str) -> None:
    if not SMTP_PASS or "PUT_YOUR_16_CHAR_APP_PASSWORD_HERE" in SMTP_PASS:
        print("⚠️  Please set SMTP_PASS to your Gmail App Password.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    print(f"📧  Email sent to {EMAIL_TO}")

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def extract_shopify_handle(product_url: str) -> tuple[str, str]:
    """
    Returns (base_url, handle)
    e.g. https://www.paaie.com/products/1-gram...  -> ("https://www.paaie.com", "1-gram-fortuna-pamp-gold-bar")
    """
    u = urlparse(product_url)
    base = f"{u.scheme}://{u.netloc}"
    m = re.search(r"/products/([^/?#]+)", u.path)
    if not m:
        raise ValueError("Product handle not found in URL")
    handle = m.group(1)
    return base, handle

def get_quantity_from_shopify(product_url: str) -> tuple[int | None, bool]:
    """
    Try Shopify JSON; if blocked, fall back to parsing HTML like "Hurry, Only 6 left!".
    Returns: (qty, in_stock)
    """
    base, handle = extract_shopify_handle(product_url)

    # 1) JSON route (may be blocked by store)
    try:
        p_res = requests.get(f"{base}/products/{handle}.js", headers=HEADERS, timeout=TIMEOUT)
        p_res.raise_for_status()
        p_json = p_res.json()

        if p_json.get("variants"):
            # choose first available, else first
            variant = None
            for v in p_json["variants"]:
                variant = v
                if v.get("available"):
                    break
            variant_id = variant["id"]

            v_res = requests.get(f"{base}/variants/{variant_id}.json", headers=HEADERS, timeout=TIMEOUT)
            if v_res.status_code == 200:
                v_json = v_res.json().get("variant", {})
                qty = v_json.get("inventory_quantity")
                available = bool(v_json.get("available", False))
                if isinstance(qty, int) and qty < 0:
                    qty = 0
                if qty is not None:
                    return qty, available
            else:
                # product.js 'available' (only boolean)
                available = any(v.get("available") for v in p_json["variants"])
                # keep qty None; we’ll still email on back-in-stock
                if available:
                    return None, True
    except Exception as e:
        print("⚠️ JSON API failed:", e)

    # 2) HTML fallback: parse visible text
    print("🔍 Falling back to HTML parsing…")
    r = requests.get(product_url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    html = r.text

    # quantity like "Only 6 left", "Hurry, Only 6 left!"
    m = re.search(r"[Hh]urry,\s*[Oo]nly\s+(\d+)\s+left|[Oo]nly\s+(\d+)\s+left", html)
    qty = None
    if m:
        qty = int(next(g for g in m.groups() if g is not None))

    # in-stock hints
    in_stock = any(s in html for s in ["In Stock", "Add to Cart", "Add to cart", "Buy now", "ADD TO CART"])

    print(f"📊 Parsed (HTML) → Qty: {qty} | In stock: {in_stock}")
    return qty, in_stock

# ===================== MONITOR LOOP =====================
print("🚀 Paaie product monitor started…")
print(f"🔗 URL: {PRODUCT_URL}")

while True:
    try:
        qty, in_stock = get_quantity_from_shopify(PRODUCT_URL)

        state = load_state()
        last_qty   = state.get("qty")
        last_stock = state.get("in_stock")

        print(f"📊 Qty: {qty} | Last: {last_qty} | In stock: {in_stock}")

        # quantity increased (or first known)
        if qty is not None and (last_qty is None or qty > last_qty):
            send_email(
                "🔔 Quantity Increased!",
                f"Quantity increased: {last_qty} → {qty}\n{PRODUCT_URL}"
            )

        # back in stock (first time or OOS -> IN)
        if in_stock and (last_stock in (None, False)):
            qtxt = f"Current quantity: {qty}" if qty is not None else "Now available"
            send_email("🟢 Product Back in Stock!", f"{qtxt}\n{PRODUCT_URL}")

        # persist state
        state["qty"]      = qty
        state["in_stock"] = in_stock
        save_state(state)

    except requests.exceptions.RequestException as e:
        print("🌐 Network error:", e)
    except Exception as e:
        print("❌ Error:", e)

    time.sleep(CHECK_INTERVAL)
