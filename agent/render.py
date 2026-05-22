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
 
 
def render_digest(blocks, target_date):
    """
    Assemble all non-None blocks into the final digest text.
 
    Args:
        blocks:       dict with keys 'baby', 'cycling', 'running', 'swimming'
                      — values are block dicts or None.
        target_date:  datetime.date for the header.
 
    Order matches SPEC §3: Baby, Cycling, Running, Swimming.
    """
    header = f"Morning Briefing — {target_date.strftime('%A, %d %B %Y')}"
    sep = "=" * len(header)
 
    parts = [header, sep, ""]
 
    renderers = [
        ("baby", render_baby_block),
        ("cycling", render_cycling_block),       # already exists
        ("running", render_running_block),
        ("swimming", render_swimming_block),
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