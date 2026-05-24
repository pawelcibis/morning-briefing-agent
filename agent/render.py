def render_cycling_block(block: dict) -> str:
    lines = [
        f"🚴  CYCLING — {block['location']}",
        f"    {block['date']}",
        "─" * 52,
    ]

    for slot in block["slots"]:
        if "error" in slot:
            lines += [f"  {slot['time']}  ⚠  {slot['error']}", ""]
            continue
        lines.append(f"  {slot['time']}")
        lines.append(
            f"    🌡  {slot['temp_c']:.1f}°C  │  "
            f"💨 {slot['wind_ms']} m/s {slot['wind_dir']}  │  "
            f"🌧 {slot['rain_pct']}%  │  "
            f"☁  {slot['cloud_label']}"
        )
        lines.append("")

    c = block.get("clothing", {})
    lines.append("  👕 Wear in the morning:")
    lines.append(f"     {c.get('wear', 'n/a')}")
    lines.append("  🎒 Pack for the return:")
    lines.append(f"     {c.get('pack', 'n/a')}")
    lines.append("")

    return "\n".join(lines)
def _fmt_pct(v):
    return "missing" if v is None else f"{v}%"
 
 
def _fmt_temp(v):
    return "missing" if v is None else f"{v}°C"
 
 
def _fmt_wind(ms, direction):
    if ms is None:
        return "missing"
    return f"{ms} m/s {direction}" if direction else f"{ms} m/s"
 
 
def render_running_block(block):
    if block is None:
        return ""
    slot = block["slot"]
    clothing = block["clothing"]
 
    lines = []
    lines.append(f"RUNNING — {block['location']['city']} {block['location']['postcode']}")
    lines.append(f"  {slot['time']}")
    lines.append(f"    Temperature:  {_fmt_temp(slot['temp_c'])}")
    lines.append(f"    Wind:         {_fmt_wind(slot['wind_ms'], slot['wind_dir'])}")
    lines.append(f"    Rain prob.:   {_fmt_pct(slot['rain_pct'])}")
    lines.append(f"    Cloud cover:  {slot['cloud_label']}")
    lines.append(f"  Clothing")
    lines.append(f"    Dry:               {clothing['dry']}")
    if clothing["wet_active"] and clothing["wet"]:
        lines.append(f"    Wet adjustments:   {clothing['wet']}")
    return "\n".join(lines)
 
 
def render_baby_block(block):
    if block is None:
        return ""
    drop = block["drop_off"]
    pick = block["pick_up"]
    clothing = block["clothing"]
 
    lines = []
    lines.append(f"BABY — {block['location']['city']} {block['location']['postcode']}")
    lines.append(f"  Baby age: {block['baby_age_months']} months")
    lines.append("")
    lines.append(f"  Drop-off ({drop['time']})")
    lines.append(f"    Temperature:  {_fmt_temp(drop['temp_c'])}")
    lines.append(f"    Wind:         {_fmt_wind(drop['wind_ms'], drop['wind_dir'])}")
    lines.append(f"    Rain prob.:   {_fmt_pct(drop['rain_pct'])}")
    lines.append(f"    Cloud cover:  {drop['cloud_label']}")
    lines.append("")
    lines.append(f"  Pick-up ({pick['time']})")
    lines.append(f"    Temperature:  {_fmt_temp(pick['temp_c'])}")
    lines.append(f"    Wind:         {_fmt_wind(pick['wind_ms'], pick['wind_dir'])}")
    lines.append(f"    Rain prob.:   {_fmt_pct(pick['rain_pct'])}")
    lines.append(f"    Cloud cover:  {pick['cloud_label']}")
    lines.append("")
    lines.append("  Clothing")
    lines.append(f"    Outfit:            {clothing['outfit']}")
    if clothing.get("pushchair_extras"):
        lines.append(f"    Pushchair extras:  {clothing['pushchair_extras']}")
    if clothing.get("pick_up_note"):
        lines.append(f"    Pick-up note:      {clothing['pick_up_note']}")
    return "\n".join(lines)
 
 
def render_swimming_block(block):
    if block is None:
        return ""
    air = block.get("air")
    water = block["water_temp_c"]
 
    lines = []
    lines.append(f"SWIMMING — {block['location']['city']} {block['location']['postcode']} (Lake Zurich)")
    lines.append(f"  {block['swim_time']}")
    lines.append(f"    Water temp:   {_fmt_temp(water)}")
    if air:
        lines.append(f"    Air temp:     {_fmt_temp(air['temp_c'])}")
        lines.append(f"    Wind:         {_fmt_wind(air['wind_ms'], air['wind_dir'])}")
        lines.append(f"    Rain prob.:   {_fmt_pct(air['rain_pct'])}")
        lines.append(f"    Cloud cover:  {air['cloud_label']}")
    else:
        lines.append(f"    Air weather:  missing")
    return "\n".join(lines)

def render_stocks_block(block: dict) -> str:
    """Render the stocks block as plain text."""
    if block is None:
        return ""
 
    tickers = block.get("tickers", [])
    if not tickers:
        return ""
 
    lines = ["📈  STOCKS"]
    lines.append("─" * 52)
 
    for t in tickers:
        if t["error"]:
            lines.append(f"  {t['ticker']}.{t['exchange']}  ⚠  {t['error']}")
            lines.append("")
            continue
 
        # Sign formatting for change values
        sign      = "+" if t["change_pct"] >= 0 else ""
        val_sign  = "+" if t["portfolio_change"] >= 0 else ""
 
        lines.append(
            f"  {t['ticker']}.{t['exchange']}  ({t['date']})"
        )
        lines.append(
            f"    Close:     {t['close']:.2f} {t['currency']}  "
            f"({sign}{t['change_pct']:.2f}%)"
        )
        lines.append(
            f"    Portfolio: {t['portfolio_value']:,.2f} {t['currency']}  "
            f"({val_sign}{t['portfolio_change']:,.2f} {t['currency']})"
        )
        lines.append(f"    Shares:    {t['shares']}")
        lines.append("")
 
    return "\n".join(lines) 
 
def render_digest(blocks, target_date):
    """
    Assemble all non-None blocks into the final digest text.
 
    Args:
        blocks:       dict with keys 'baby', 'cycling', 'running', 'swimming',
                      'stocks' — values are block dicts or None.
        target_date:  datetime.date for the header.
 
    Order matches SPEC §3: Baby, Cycling, Running, Swimming, Stocks.
    """
    header = f"Morning Briefing — {target_date.strftime('%A, %d %B %Y')}"
    sep = "=" * len(header)
 
    parts = [header, sep, ""]
 
    renderers = [
        ("baby",     render_baby_block),
        ("cycling",  render_cycling_block),
        ("running",  render_running_block),
        ("swimming", render_swimming_block),
        ("stocks",   render_stocks_block),      # ← new in Phase 6
    ]
 
    for key, fn in renderers:
        block = blocks.get(key)
        if block is None:
            continue
        rendered = fn(block)
        if rendered:
            parts.append(rendered)
            parts.append("")  # blank line between blocks
 
    parts.append("— end —")
    return "\n".join(parts)

# Which block keys each role receives.
# render_digest() already skips None values, so we zero out the rest.
ROLE_BLOCKS = {
    "full":      {"baby", "cycling", "running", "swimming", "stocks"},
    "baby_only": {"baby"},
}
 
 
def render_for_recipient(blocks: dict, target_date, role: str) -> str:
    """
    Render the digest for a specific recipient role.
 
    Args:
        blocks:      Full blocks dict (all keys present, values may be None).
        target_date: datetime.date for the header.
        role:        "full" or "baby_only" (from config.yaml).
 
    Returns:
        Formatted digest string containing only the blocks for that role.
    """
    allowed = ROLE_BLOCKS.get(role, set())
    filtered = {k: (v if k in allowed else None) for k, v in blocks.items()}
    return render_digest(filtered, target_date)