"""
holiday_test.py — holiday mode test (Phase 14).

DEFAULT (mocked — no network, no LLM, no dispatch, repo state/logs untouched):
  1. PERIODS     real config.yaml: boundaries 3/4, 9/10, 17/18, 21/22 Oct, swim
                 spot only on Kos, malformed period skipped, YAML 06:00 guard.
  2. BUILDERS    canned Open-Meteo rows: Kos fetched in Europe/Athens, Wrocław in
                 Europe/Warsaw, ONE weather call per run, six slots, rain +
                 thunderstorm alerts, running wet rule, sea temp from a 6-hourly
                 (null-gapped) series, outage behaviour. Prints Pawel's and
                 Liliana's rendered digests for eyeballing.
  3. END-TO-END  agent.main in --dry-run with a frozen clock and a temp dir:
                 Sat 3 Oct evening (→ Wrocław), Fri 9 Oct evening (→ Kos, stocks
                 kept), Sat 10 Oct morning (deltas), Wed 21 Oct evening (→ normal).

LIVE (needs internet; uses ANTHROPIC_API_KEY if set; still no dispatch/state):
  Builds TOMORROW's holiday digest for every distinct holiday location in
  config.yaml from real Open-Meteo data and prints it, so the Kos output can be
  checked before 10 Oct.

Run:
  python holiday_test.py
  python holiday_test.py --live
"""

import contextlib
import copy
import datetime
import io
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:                                   # emoji-safe output even when redirected on Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Dummy recipient secrets so dry-run dispatch reports "dry-run", not "missing env".
for _k in ("RECIPIENT_PAWEL_EMAIL", "RECIPIENT_PAWEL_TELEGRAM",
           "RECIPIENT_LILIANA_EMAIL", "RECIPIENT_LILIANA_TELEGRAM"):
    os.environ.setdefault(_k, f"dummy-{_k.lower()}")

D = datetime.date
TD = datetime.timedelta
SLOT_TIMES = ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
_FAILS: list[str] = []


def _section(title: str) -> None:
    print("\n" + "=" * 70 + f"\n  {title}\n" + "=" * 70)


def check(cond, msg: str) -> None:
    print(f"  {'OK  ' if cond else 'FAIL'}  {msg}")
    if not cond:
        _FAILS.append(msg)


# ---------------------------------------------------------------------------
# Canned data
# ---------------------------------------------------------------------------

def _fake_rows(target, temp_shift=0.0, rain_hours=(14, 15, 16), rain_pct=55,
               storm_hours=(16,)):
    """Open-Meteo-shaped hourly rows for target-1 .. target+1.
    Temperatures at the slots: 06→17.0, 09→20.0, 12→23.0, 15→24.0, 18→21.0, 21→18.0."""
    rows = []
    for offset in (-1, 0, 1):
        day = target + TD(days=offset)
        for h in range(24):
            temp = 17.0 + 8.0 * max(0.0, 1 - abs(h - 14) / 8) + temp_shift
            rows.append({
                "time": f"{day.isoformat()}T{h:02d}:00",
                "temperature_c": round(temp, 1),
                "windspeed_ms": round(2.5 + (h % 4) * 0.5, 1),
                "winddirection_deg": 350,
                "precipitation_probability_pct": rain_pct if h in rain_hours else 5,
                "cloudcover_pct": 10 if h < 12 else 40,
                "weather_code": 95 if h in storm_hours else 1,
                "precipitation_mm_h": 0.0,
            })
    return rows


def _fake_marine(target, base=24.0):
    """6-hourly sea temperature (other hours null), like a coarse SST model:
    00→base, 06→base+0.1, 12→base+0.2, 18→base+0.3."""
    rows = []
    for offset in (-1, 0, 1):
        day = target + TD(days=offset)
        for h in range(24):
            val = None if h % 6 else round(base + 0.1 * (h // 6), 1)
            rows.append({"time": f"{day.isoformat()}T{h:02d}:00", "sea_temp_c": val})
    return rows


_CANNED_CLOTHING = {
    "outfit": "short-sleeved cotton bodysuit, light trousers",
    "adjustments": "add a thin cardigan before 09:00 and after 18:00",
    "extras": "sun hat; keep in the shade at midday; rain cover",
}

_CANNED_STOCKS = {"tickers": [{
    "ticker": "KRU", "exchange": "WSE", "date": "2026-10-09", "close": 412.5,
    "change_pct": 1.73, "portfolio_value": 41250.0, "portfolio_change": 700.5,
    "shares": 100, "currency": "PLN", "error": None}]}


class _Recorder:
    """Callable stand-in that records its calls."""
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        return self.fn(*a, **k)


# ---------------------------------------------------------------------------
# 1 — Period lookup
# ---------------------------------------------------------------------------

def test_periods(cfg) -> None:
    _section("1 — Period lookup (real config.yaml)")
    from agent.blocks.holiday import active_period, location_label, _hhmm

    cases = [(D(2026, 10, 3), None), (D(2026, 10, 4), "Wrocław, PL"),
             (D(2026, 10, 9), "Wrocław, PL"), (D(2026, 10, 10), "Tigaki, GR"),
             (D(2026, 10, 17), "Tigaki, GR"), (D(2026, 10, 18), "Wrocław, PL"),
             (D(2026, 10, 21), "Wrocław, PL"), (D(2026, 10, 22), None)]
    for day, expected in cases:
        p = active_period(cfg, day, warn=False)
        got = location_label(p) if p else None
        check(got == expected, f"{day} {day:%a} → {got or 'normal mode'}")

    check(bool(active_period(cfg, D(2026, 10, 12))["swimming"]), "Kos period has a swim spot")
    check(not active_period(cfg, D(2026, 10, 5)).get("swimming"), "Wrocław periods have no swim spot")
    check(cfg["holiday"]["slot_times"] == SLOT_TIMES, f"slot_times = {cfg['holiday']['slot_times']}")

    bad = copy.deepcopy(cfg)
    bad["holiday"]["periods"].insert(0, {"start": "2026-10-01", "end": "2026-10-31",
                                         "location": {"city": "Nowhere"}})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        p = active_period(bad, D(2026, 10, 12))
    check(p is not None and location_label(p) == "Tigaki, GR" and "malformed" in buf.getvalue(),
          "malformed period skipped with a warning, next period still matched")
    check(_hhmm(360) == "06:00", "unquoted YAML 06:00 (read as 360) normalised to '06:00'")


# ---------------------------------------------------------------------------
# 2 — Builders + render
# ---------------------------------------------------------------------------

def _patch_holiday(H, wx_fn, marine_fn):
    """Mock the CONSUMER module's references (agent.blocks.holiday.*)."""
    H._reset_cache()
    H.fetch_hourly = _Recorder(wx_fn)
    H.fetch_marine_hourly = _Recorder(marine_fn)
    H.baby_holiday_clothing_recommendation = _Recorder(lambda **k: dict(_CANNED_CLOTHING))
    return H.fetch_hourly, H.fetch_marine_hourly, H.baby_holiday_clothing_recommendation


def _build_all(H, cfg, day):
    return {
        "baby": None, "cycling": None, "running": None, "swimming": None,
        "stocks": None, "wednesday_event": None,
        "holiday_weather":  H.build_holiday_weather_block(cfg, day),
        "holiday_baby":     H.build_holiday_baby_block(cfg, day),
        "holiday_running":  H.build_holiday_running_block(cfg, day),
        "holiday_swimming": H.build_holiday_swimming_block(cfg, day),
    }


def test_builders(cfg) -> None:
    _section("2 — Builders + render (mocked Open-Meteo / marine / LLM)")
    import agent.blocks.holiday as H
    from agent.render import render_for_recipient

    real = (H.fetch_hourly, H.fetch_marine_hourly, H.baby_holiday_clothing_recommendation)
    try:
        # --- Kos ------------------------------------------------------------
        kos = D(2026, 10, 11)
        wx, mar, llm = _patch_holiday(
            H, lambda latitude, longitude, timezone: _fake_rows(kos),
            lambda lat, lon, timezone: _fake_marine(kos))
        blocks = _build_all(H, cfg, kos)
        w, b, r, s = (blocks[k] for k in ("holiday_weather", "holiday_baby",
                                          "holiday_running", "holiday_swimming"))

        check(len(wx.calls) == 1, f"one Open-Meteo call for weather + baby + running (got {len(wx.calls)})")
        check(wx.calls[0][1].get("timezone") == "Europe/Athens", "Kos fetched in Europe/Athens local time")
        check(w is not None and [x["time"] for x in w["slots"]] == SLOT_TIMES, "six slots 06–21 h")
        check(w and [x["temp_c"] for x in w["slots"]] == [17.0, 20.0, 23.0, 24.0, 21.0, 18.0],
              "slot temperatures read from the right hours")
        check(w and w["alerts"] == ["Rain likely 14:00–16:00 (peak 55%)", "Thunderstorm possible 16:00"],
              f"alerts over 06–21 h: {w and w['alerts']}")
        k = llm.calls[0][1] if llm.calls else {}
        check(len(k.get("slots", [])) == 6 and k.get("place") == "Tigaki, GR" and k.get("alerts"),
              "LLM receives 6 slots, place and alerts")
        check(b and b["clothing"] == _CANNED_CLOTHING and b["baby_age_months"] > 9,
              f"baby block: age {b and b['baby_age_months']} months + clothing")
        wet = [x["time"] for x in r["slots"] if x.get("wet_active")] if r else None
        check(wet == ["15:00"], f"running wet rule (rain ≥ 30%) only at 15:00: {wet}")
        check(s is not None and s["water_temp_c"] == 24.2,
              f"sea temp = mean of non-null slot hours 06/12/18 → {s and s['water_temp_c']}")
        a, kw = mar.calls[0]
        check(a[:2] == (36.9, 27.1823) and kw.get("timezone") == "Europe/Athens",
              "marine fetched at the swim point, Athens time")

        _section("2a — Pawel's holiday digest (Kos, evening; canned stocks added to show placement)")
        full_blocks = dict(blocks, stocks=_CANNED_STOCKS)
        full = render_for_recipient(full_blocks, kos, "full", run_type="evening")
        print(full)
        _section("2b — Liliana's holiday digest (Kos, evening)")
        lili = render_for_recipient(full_blocks, kos, "baby_only", run_type="evening")
        print(lili)
        _section("2c — Render checks")
        check("🌴 Holiday mode — Tigaki, GR" in full and "🌴 Holiday mode — Tigaki, GR" in lili,
              "holiday banner line in both digests")
        check(full.count("WEATHER") == 1 and "Local time (Europe/Athens)" in full,
              "one shared weather table, labelled with local timezone")
        check("09:00–12:00" in full and "+ wet: no sunglasses, cap (recommended)" in full,
              "running: identical consecutive slots merged; wet adjustment shown at 15:00")
        check("SWIMMING — Tigaki beach (sea)" in full and "24.2°C (day avg)" in full, "sea block rendered")
        check("STOCKS" in full and "CYCLING" not in full, "stocks kept, cycling absent")
        check(all(x in lili for x in ("WEATHER", "BABY")) and
              not any(x in lili for x in ("RUNNING", "SWIMMING", "STOCKS")),
              "Liliana: weather + baby only")

        # --- Wrocław --------------------------------------------------------
        wro = D(2026, 10, 6)
        wx, mar, _ = _patch_holiday(
            H, lambda latitude, longitude, timezone: _fake_rows(wro),
            lambda lat, lon, timezone: _fake_marine(wro))
        blocks = _build_all(H, cfg, wro)
        check(wx.calls and wx.calls[0][1].get("timezone") == "Europe/Warsaw", "Wrocław fetched in Europe/Warsaw")
        check(blocks["holiday_swimming"] is None and not mar.calls, "Wrocław: no swim block, marine never called")
        check(blocks["holiday_weather"]["place"] == "Wrocław, PL", "place label 'Wrocław, PL'")

        # --- outside any period --------------------------------------------
        blocks = _build_all(H, cfg, D(2026, 10, 22))
        check(all(v is None for v in blocks.values()), "22 Oct: every holiday builder returns None")

        # --- Open-Meteo outage ----------------------------------------------
        def _down(**k):
            raise ConnectionError("simulated outage")
        wx, _, llm = _patch_holiday(H, _down, lambda lat, lon, timezone: None)
        with contextlib.redirect_stdout(io.StringIO()):
            blocks = _build_all(H, cfg, kos)
        check(all(blocks[k] is None for k in ("holiday_weather", "holiday_baby", "holiday_running")),
              "outage: weather/baby/running → None, no crash")
        check(len(wx.calls) == 1 and not llm.calls, "outage: failure memoised (1 fetch attempt), LLM not called")
        check(blocks["holiday_swimming"] and blocks["holiday_swimming"]["water_temp_c"] is None,
              "marine failure: swim block kept with water temp 'missing'")
    finally:
        H.fetch_hourly, H.fetch_marine_hourly, H.baby_holiday_clothing_recommendation = real
        H._reset_cache()


# ---------------------------------------------------------------------------
# 3 — End-to-end through agent.main (dry-run, frozen clock, temp dir)
# ---------------------------------------------------------------------------

def test_end_to_end() -> None:
    _section("3 — End-to-end: agent.main dry-run with a frozen clock")
    import agent.main as M
    import agent.state as S
    import agent.blocks.holiday as H

    tmp = tempfile.mkdtemp(prefix="holiday_test_")
    state_path = os.path.join(tmp, "state", "last_run.json")
    names = ("datetime", "STATE_PATH", "read_state", "build_baby_block", "build_cycling_block",
             "build_running_block", "build_swimming_block", "build_stocks_block")
    saved_main = {n: getattr(M, n) for n in names}
    saved_h = (H.fetch_hourly, H.fetch_marine_hourly, H.baby_holiday_clothing_recommendation)
    normal_calls: list[str] = []

    M.STATE_PATH = state_path
    M.read_state = lambda: S.read_state(state_path)
    for n in ("build_baby_block", "build_cycling_block", "build_running_block", "build_swimming_block"):
        setattr(M, n, (lambda n: (lambda cfg, td: normal_calls.append(n) or None))(n))
    M.build_stocks_block = lambda cfg: _CANNED_STOCKS
    H.baby_holiday_clothing_recommendation = lambda **k: dict(_CANNED_CLOTHING)

    def run(today, run_type, shift=0.0):
        class _Frozen(datetime.date):
            @classmethod
            def today(cls):
                return today
        M.datetime = types.SimpleNamespace(date=_Frozen, timedelta=datetime.timedelta)
        target = today + TD(days=1) if run_type == "evening" else today
        H._reset_cache()                      # every real run is a fresh process
        H.fetch_hourly = lambda latitude, longitude, timezone: _fake_rows(target, temp_shift=shift)
        H.fetch_marine_hourly = lambda lat, lon, timezone: _fake_marine(target, base=24.0 + shift / 4)
        normal_calls.clear()
        buf, cwd = io.StringIO(), os.getcwd()
        os.chdir(tmp)                          # logs/ and messages/ land in the temp dir
        try:
            with contextlib.redirect_stdout(buf):
                M.main(run_type=run_type, dry_run=True)
        finally:
            os.chdir(cwd)
        msg_path = os.path.join(tmp, "logs", "messages", f"{target}-{run_type}.txt")
        msg = open(msg_path, encoding="utf-8").read() if os.path.exists(msg_path) else ""
        return buf.getvalue(), msg

    try:
        # Sat 3 Oct evening → Sun 4 Oct: first Wrocław day, weekend → no stocks
        out, msg = run(D(2026, 10, 3), "evening")
        check("HOLIDAY MODE — Wrocław, PL" in out, "Sat 3 Oct evening → holiday mode Wrocław (target Sun 4)")
        check("[stocks    ] skipped" in out, "stocks rule untouched: Saturday evening → skipped")

        # Fri 9 Oct evening → Sat 10 Oct: first Kos day, weekday evening → stocks
        out, msg = run(D(2026, 10, 9), "evening")
        check("HOLIDAY MODE — Tigaki, GR" in out, "Fri 9 Oct evening → holiday mode Tigaki (target Sat 10)")
        check(not normal_calls, f"normal baby/cycling/running/swimming not built (called: {normal_calls})")
        check("[stocks    ] built" in out and "📈  STOCKS" in msg, "stocks rule untouched: Friday evening → built")
        check("Morning briefing — Sat 10 Oct · Tigaki, GR" in out, "subject carries the holiday place")
        check("[Liliana" in out and "no content for role 'baby_only'" not in out,
              "Liliana served on a Saturday (holiday baby block daily)")
        check("🌴 Holiday mode — Tigaki, GR" in msg and "CYCLING" not in msg, "archived digest in holiday layout")

        # Sat 10 Oct morning, forecast warmed by 2 °C → deltas vs the evening state
        out, msg = run(D(2026, 10, 10), "morning", shift=2.0)
        check("computed 0 field delta" not in out, "morning: deltas computed against the Kos evening state")
        check("(↑ +2.0)" in msg and "24.7°C (day avg)  (↑ +0.5)" in msg,
              "morning digest annotates temp and sea-temp changes")
        print("\n  --- morning update as archived (full role) ---")
        print("\n".join("    " + line for line in msg.splitlines()))

        # Wed 21 Oct evening → Thu 22 Oct: holiday over, normal mode resumes
        out, msg = run(D(2026, 10, 21), "evening")
        check("HOLIDAY MODE" not in out and sorted(normal_calls) == sorted(
            ["build_baby_block", "build_cycling_block", "build_running_block", "build_swimming_block"]),
            "Wed 21 Oct evening → normal mode, normal builders called")
        check("Holiday mode" not in msg and "· " not in out.split("subject=")[1].splitlines()[0],
              "no holiday banner, plain subject")
    finally:
        for n, v in saved_main.items():
            setattr(M, n, v)
        H.fetch_hourly, H.fetch_marine_hourly, H.baby_holiday_clothing_recommendation = saved_h
        H._reset_cache()


# ---------------------------------------------------------------------------
# LIVE mode
# ---------------------------------------------------------------------------

def live() -> int:
    from agent.config import load_config
    import agent.blocks.holiday as H
    from agent.render import render_for_recipient

    cfg = load_config()
    tomorrow = datetime.date.today() + TD(days=1)
    seen = set()
    for period in cfg["holiday"]["periods"]:
        city = period["location"]["city"]
        if city in seen:
            continue
        seen.add(city)
        test_cfg = copy.deepcopy(cfg)
        test_cfg["holiday"]["periods"] = [{**period, "start": tomorrow, "end": tomorrow}]
        H._reset_cache()
        blocks = _build_all(H, test_cfg, tomorrow)
        _section(f"LIVE — {city}, forecast for {tomorrow} (full role)")
        print(render_for_recipient(blocks, tomorrow, "full", run_type="evening"))
    return 0


if __name__ == "__main__":
    if "--live" in sys.argv:
        sys.exit(live())

    from agent.config import load_config
    _cfg = load_config()
    test_periods(_cfg)
    test_builders(_cfg)
    test_end_to_end()

    _section("Summary")
    if _FAILS:
        print(f"  {len(_FAILS)} FAILURE(S):")
        for f in _FAILS:
            print(f"    - {f}")
        print("\n  Holiday test: FAILURES PRESENT")
        sys.exit(1)
    print("  Holiday test: ALL PASS")
    sys.exit(0)