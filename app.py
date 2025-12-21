@app.route("/api/admin/create-bypass", methods=["POST"])
def create_bypass():
    d = ensure_keys(load_data())
    cleanup_expired_bypasses(d)

    b = request.json or {}
    user = (b.get("user") or "").strip()
    urls = b.get("urls") or []

    # Use per-request TTL if given, else global default
    ttl = b.get("ttl_minutes")
    if ttl is None:
        ttl = d.get("settings", {}).get("bypass_ttl_minutes", 10)
    try:
        ttl = int(ttl)
    except Exception:
        ttl = 10

    # Clamp TTL
    ttl = max(1, min(ttl, 1440))

    code = generate_bypass_code()
    expires_at = now_ts() + ttl * 60

    d.setdefault("bypass_codes", {})[code] = {
        "expires_at": expires_at,
        "user": user,
        "urls": urls
    }

    save_data(d)

    return jsonify({
        "ok": True,
        "code": code,
        "expires_in_minutes": ttl
    })
