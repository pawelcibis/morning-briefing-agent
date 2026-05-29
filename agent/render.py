"""
agent/render.py — Format structured blocks as plain text.

House style (Phase 13, item H): every block renders the same way —
    {emoji}  TITLE — location
        optional subtitle (date / age)
    ──────────────────────────────
      slot / section
        Label:        value  (↑ +delta)
The emoji header + rule gives scannability; the plain "Label: value" body is
robust across email and Telegram (no box-drawing that mis-aligns in some
clients). Cycling and stocks were converted from the old emoji/box layout.

Delta annotations (morning edition): render_* functions accept
    deltas:     flat {dot-path: float} dict from diff.diff_blocks() (or None).
    thresholds: {field: min abs-delta to display}, normally cfg["diff_thresholds"].
The dot-path keys (e.g. "cycling.06:30.temp_c") MUST match diff.py exactly.

run_type (Phase 13, item G): threaded into render_digest so the in-body banner
("Morning Briefing" vs "Morning Update") matches the email subject line.
"""

RULE_WIDTH = 52

# ---------------------------------------------------------------------------
# Delta annotation helpers
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "temp_c":       0.5,
    "rain_pct":     5.0,
    "wind_ms":      1.0,
    "water_temp_c": 0.5,
}


def _fmt_delta(delta, field: str, thresholds: dict | None = None) -> str:
    """Return an annotation like '  (↑ +2.1)' or '' (empty).

    Empty when delta is None or abs(delta) is below the field threshold.
    """
    if delta is None:
        return ""
    thr = (thresholds or DEFAULT_THRESHOLDS).get(field, 0.5)
    if abs(delta) < thr:
        return ""
    arrow = "↑" if delta > 0 else "↓"
    sign  = "+" if delta > 0 else ""
    if field == "rain_pct":
        return f"  ({arrow} {sign}{delta:.0f})"
    return f"  ({arrow} {sign}{delta:.1f})"


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------

def _fmt_pct(v):
    return "missing" if v is None else f"{v}%"


def _fmt_temp(v):
    return "missing" if v is None else f"{v:.1f}°C"


def _fmt_wind(ms, direction):
    if ms is None:
        return "missing"
    return f"{ms} m/s {direction}" if direction else f"{ms} m/s"


def _block_header(emoji: str, title: str, subtitle: str | None = None) -> list[str]:
    """Consistent block header: emoji + UPPERCASE title, optional subtitle, rule."""
    lines = [f"{emoji}  {title}"]
    if subtitle:
        lines.append(f"    {subtitle}")
    lines.append("─" * RULE_WIDTH)
    return lines


def _render_alerts(alerts: list) -> list[str]:
    """Indented alert lines ('  ⚠  text'); [] when there are no alerts."""
    if not alerts:
        return []
    return [f"  ⚠  {a}" for a in alerts]


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------

def render_cycling_block(block: dict,
                         deltas: dict | None = None,
                         thresholds: dict | None = None) -> str:
    if block is None:
        return ""
    d = deltas or {}
    lines = _block_header("🚴", f"CYCLING — {block['location']}", block.get("date"))

    for slot in block["slots"]:
        if "error" in slot:
            lines += [f"  {slot['time']}", f"    ⚠  {slot['error']}", ""]
            continue
        t = slot["time"]
        temp_ann = _fmt_delta(d.get(f"cycling.{t}.temp_c"),  "temp_c",   thresholds)
        wind_ann = _fmt_delta(d.get(f"cycling.{t}.wind_ms"), "wind_ms",  thresholds)
        rain_ann = _fmt_delta(d.get(f"cycling.{t}.rain_pct"),"rain_pct", thresholds)
        lines.append(f"  {t}")
        lines.append(f"    Temperature:  {_fmt_temp(slot['temp_c'])}{temp_ann}")
        lines.append(f"    Wind:         {_fmt_wind(slot['wind_ms'], slot['wind_dir'])}{wind_ann}")
        lines.append(f"    Rain prob.:   {_fmt_pct(slot['rain_pct'])}{rain_ann}")
        lines.append(f"    Cloud cover:  {slot['cloud_label']}")
        lines.append("")

    alert_lines = _render_alerts(block.get("alerts", []))
    if alert_lines:
        lines.extend(alert_lines)
        lines.append("")

    c = block.get("clothing", {})
    lines.append("  Clothing")
    lines.append(f"    Wear (morning):  {c.get('wear', 'n/a')}")
    lines.append(f"    Pack (return):   {c.get('pack', 'n/a')}")
    return "\n".join(lines)


def render_running_block(block,
                         deltas: dict | None = None,
                         thresholds: dict | None = None):
    if block is None:
        return ""
    d    = deltas or {}
    slot = block["slot"]
    clothing = block["clothing"]
    t = slot["time"]

    temp_ann = _fmt_delta(d.get(f"running.{t}.temp_c"),  "temp_c",   thresholds)
    wind_ann = _fmt_delta(d.get(f"running.{t}.wind_ms"), "wind_ms",  thresholds)
    rain_ann = _fmt_delta(d.get(f"running.{t}.rain_pct"),"rain_pct", thresholds)

    loc = block["location"]
    lines = _block_header("🏃", f"RUNNING — {loc['city']} {loc['postcode']}")
    lines.append(f"  {t}")
    lines.append(f"    Temperature:  {_fmt_temp(slot['temp_c'])}{temp_ann}")
    lines.append(f"    Wind:         {_fmt_wind(slot['wind_ms'], slot['wind_dir'])}{wind_ann}")
    lines.append(f"    Rain prob.:   {_fmt_pct(slot['rain_pct'])}{rain_ann}")
    lines.append(f"    Cloud cover:  {slot['cloud_label']}")

    alert_lines = _render_alerts(block.get("alerts", []))
    if alert_lines:
        lines.append("")
        lines.extend(alert_lines)

    lines.append("")
    lines.append("  Clothing")
    lines.append(f"    Dry:               {clothing['dry']}")
    if clothing["wet_active"] and clothing["wet"]:
        lines.append(f"    Wet adjustments:   {clothing['wet']}")
    return "\n".join(lines)


def render_baby_block(block,
                      deltas: dict | None = None,
                      thresholds: dict | None = None):
    if block is None:
        return ""
    d    = deltas or {}
    drop = block["drop_off"]
    pick = block["pick_up"]
    clothing = block["clothing"]

    def _ann(slot_key, field):
        return _fmt_delta(d.get(f"baby.{slot_key}.{field}"), field, thresholds)

    loc = block["location"]
    lines = _block_header("👶", f"BABY — {loc['city']} {loc['postcode']}",
                          f"Baby age: {block['baby_age_months']} months")

    lines.append(f"  Drop-off ({drop['time']})")
    lines.append(f"    Temperature:  {_fmt_temp(drop['temp_c'])}{_ann('drop_off', 'temp_c')}")
    lines.append(f"    Wind:         {_fmt_wind(drop['wind_ms'], drop['wind_dir'])}{_ann('drop_off', 'wind_ms')}")
    lines.append(f"    Rain prob.:   {_fmt_pct(drop['rain_pct'])}{_ann('drop_off', 'rain_pct')}")
    lines.append(f"    Cloud cover:  {drop['cloud_label']}")
    lines.append("")
    lines.append(f"  Pick-up ({pick['time']})")
    lines.append(f"    Temperature:  {_fmt_temp(pick['temp_c'])}{_ann('pick_up', 'temp_c')}")
    lines.append(f"    Wind:         {_fmt_wind(pick['wind_ms'], pick['wind_dir'])}{_ann('pick_up', 'wind_ms')}")
    lines.append(f"    Rain prob.:   {_fmt_pct(pick['rain_pct'])}{_ann('pick_up', 'rain_pct')}")
    lines.append(f"    Cloud cover:  {pick['cloud_label']}")

    alert_lines = _render_alerts(block.get("alerts", []))
    if alert_lines:
        lines.append("")
        lines.extend(alert_lines)

    lines.append("")
    lines.append("  Clothing")
    lines.append(f"    Outfit:            {clothing['outfit']}")
    if clothing.get("pushchair_extras"):
        lines.append(f"    Pushchair extras:  {clothing['pushchair_extras']}")
    if clothing.get("pick_up_note"):
        lines.append(f"    Pick-up note:      {clothing['pick_up_note']}")
    return "\n".join(lines)


def render_swimming_block(block,
                          deltas: dict | None = None,
                          thresholds: dict | None = None):
    if block is None:
        return ""
    d = deltas or {}
    air = block.get("air")
    water = block["water_temp_c"]
    water_ann = _fmt_delta(d.get("swimming.water_temp_c"), "water_temp_c", thresholds)

    loc = block["location"]
    lines = _block_header("🏊", f"SWIMMING — {loc['city']} {loc['postcode']} (Lake Zurich)")
    lines.append(f"  {block['swim_time']}")
    lines.append(f"    Water temp:   {_fmt_temp(water)}{water_ann}")
    if air:
        air_temp_ann = _fmt_delta(d.get("swimming.air.temp_c"),  "temp_c",   thresholds)
        air_wind_ann = _fmt_delta(d.get("swimming.air.wind_ms"), "wind_ms",  thresholds)
        air_rain_ann = _fmt_delta(d.get("swimming.air.rain_pct"),"rain_pct", thresholds)
        lines.append(f"    Air temp:     {_fmt_temp(air['temp_c'])}{air_temp_ann}")
        lines.append(f"    Wind:         {_fmt_wind(air['wind_ms'], air['wind_dir'])}{air_wind_ann}")
        lines.append(f"    Rain prob.:   {_fmt_pct(air['rain_pct'])}{air_rain_ann}")
        lines.append(f"    Cloud cover:  {air['cloud_label']}")
    else:
        lines.append("    Air weather:  missing")
    return "\n".join(lines)


def render_stocks_block(block: dict,
                        deltas: dict | None = None,       # accepted but unused
                        thresholds: dict | None = None) -> str:
    """Render the stocks block. Tightened (item C): one line of figures per
    ticker beneath a date header. Deltas are not applied to stocks."""
    if block is None:
        return ""
    tickers = block.get("tickers", [])
    if not tickers:
        return ""

    lines = _block_header("📈", "STOCKS")
    for t in tickers:
        if t["error"]:
            lines.append(f"  {t['ticker']}.{t['exchange']}  ⚠  {t['error']}")
            continue
        sign     = "+" if t["change_pct"] >= 0 else ""
        val_sign = "+" if t["portfolio_change"] >= 0 else ""
        lines.append(f"  {t['ticker']}.{t['exchange']} ({t['date']})")
        lines.append(
            f"    {t['close']:.2f} {t['currency']}  ({sign}{t['change_pct']:.2f}%)"
            f"   ·   Portfolio {t['portfolio_value']:,.2f} {t['currency']}  "
            f"({val_sign}{t['portfolio_change']:,.2f}, {t['shares']} sh)"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Digest assembly
# ---------------------------------------------------------------------------

def render_digest(blocks, target_date,
                  deltas: dict | None = None,
                  thresholds: dict | None = None,
                  run_type: str = "evening"):
    """
    Assemble all non-None blocks into the final digest text.

    run_type drives the banner so it matches the email subject:
      evening → "Morning Briefing — <date>"   (full forecast for tomorrow)
      morning → "Morning Update — <date>"      (delta vs last night)

    Block order matches SPEC §3: Baby, Cycling, Running, Swimming, Stocks.
    """
    banner = "Morning Update" if run_type == "morning" else "Morning Briefing"
    header = f"{banner} — {target_date.strftime('%A, %d %B %Y')}"
    sep    = "=" * len(header)

    parts = [header, sep, ""]

    renderers = [
        ("baby",     render_baby_block),
        ("cycling",  render_cycling_block),
        ("running",  render_running_block),
        ("swimming", render_swimming_block),
        ("stocks",   render_stocks_block),
    ]

    for key, fn in renderers:
        block = blocks.get(key)
        if block is None:
            continue
        rendered = fn(block, deltas=deltas, thresholds=thresholds)
        if rendered:
            parts.append(rendered)
            parts.append("")  # blank line between blocks

    parts.append("— end —")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Role-filtered rendering
# ---------------------------------------------------------------------------

ROLE_BLOCKS = {
    "full":      {"baby", "cycling", "running", "swimming", "stocks"},
    "baby_only": {"baby"},
}


def render_for_recipient(blocks: dict, target_date, role: str,
                         deltas: dict | None = None,
                         thresholds: dict | None = None,
                         run_type: str = "evening") -> str:
    """Render the digest for a specific recipient role (filters blocks by role)."""
    allowed  = ROLE_BLOCKS.get(role, set())
    filtered = {k: (v if k in allowed else None) for k, v in blocks.items()}
    return render_digest(filtered, target_date, deltas=deltas,
                         thresholds=thresholds, run_type=run_type)
