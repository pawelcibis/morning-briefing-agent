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