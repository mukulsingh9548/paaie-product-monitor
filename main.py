# --- add near HEADERS ---
AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "",
    "Referer": "",
    "User-Agent": HEADERS["User-Agent"],
}

# --- add helper to pick a variant from product.js ---
def get_product_and_variant(product_url: str):
    base, handle = extract_shopify_handle(product_url)
    p_res = http_get(f"{base}/products/{handle}.js", headers=HEADERS)
    p_res.raise_for_status()
    pdata = p_res.json()
    variants = pdata.get("variants") or []
    if not variants:
        return base, None, None
    # pick first available, else first
    v = next((v for v in variants if v.get("available")), variants[0])
    return base, v.get("id"), bool(v.get("available"))

# --- add cart-probe (very gentle) ---
def get_quantity_via_cart_probe(product_url: str, variant_id: int):
    """
    Try to estimate available stock by adding large qty and reading cart.
    Clears cart afterwards. Uses one session so it doesn't affect users.
    """
    base, _handle = extract_shopify_handle(product_url)
    ajax = dict(AJAX_HEADERS)
    ajax["Origin"] = base
    ajax["Referer"] = product_url

    try:
        # clear any previous session cart (no-op if empty)
        http_post(f"{base}/cart/clear.js", headers=ajax)

        # ask for a big number; Shopify will clamp to available qty
        add = http_post(
            f"{base}/cart/add.js",
            headers=ajax,
            data={"id": str(variant_id), "quantity": "999"},
        )
        if add.status_code not in (200, 302):
            print("[cart] add failed:", add.status_code, add.text[:200])

        cart = http_get(f"{base}/cart.js", headers=ajax)
        cart.raise_for_status()
        cjson = cart.json()
        # find that variant in cart
        for line in cjson.get("items", []):
            if str(line.get("variant_id")) == str(variant_id):
                qty = int(line.get("quantity") or 0)
                # tidy up
                http_post(f"{base}/cart/clear.js", headers=ajax)
                return qty

        http_post(f"{base}/cart/clear.js", headers=ajax)
    except Exception as e:
        print("[cart-probe] error:", e)

    return None

# --- MODIFY get_quantity_and_stock() to use new fallbacks ---
def get_quantity_and_stock(product_url: str):
    # 1) product + variant info
    base, handle_qty_variant_id, variant_available = None, None, None
    try:
        base, handle_qty_variant_id, variant_available = get_product_and_variant(product_url)
    except Exception as e:
        print("[product.js] failed:", e)

    # 2) variant.json (fast + best when available)
    qty, in_stock = try_shopify_json(product_url)
    if qty is not None or in_stock is not None:
        print(f"[route:json] qty={qty}, in_stock={in_stock}")
        # if qty still unknown but variant is available, try cart-probe once
        if qty is None and (in_stock or variant_available):
            if handle_qty_variant_id:
                q2 = get_quantity_via_cart_probe(product_url, handle_qty_variant_id)
                if isinstance(q2, int):
                    qty = q2
        return qty, in_stock if in_stock is not None else bool(qty and qty > 0)

    # 3) cart-probe (when JSON didn’t give anything)
    if handle_qty_variant_id:
        q2 = get_quantity_via_cart_probe(product_url, handle_qty_variant_id)
        if isinstance(q2, int):
            return q2, q2 > 0

    # 4) HTML regex fallback (works if theme renders server-side text)
    print("[route:html] fallback…")
    r = http_get(product_url, headers=HEADERS, allow_redirects=True)
    print(f"[html] status={r.status_code}, len={len(r.text)}")
    r.raise_for_status()
    qty, in_stock = parse_html_quantity(r.text)
    print(f"[route:html] qty={qty}, in_stock={in_stock}")
    return qty, in_stock
