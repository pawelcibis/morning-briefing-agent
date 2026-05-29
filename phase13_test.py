"""
phase13_test.py

Phase 13 hardening test — exercises the three things Phase 13 added or relies on:

  1. RETRY PATHS
     * R1 graceful degradation: a fetcher that always fails → block becomes None,
       the run does NOT crash. (Patches the CONSUMER module's imported
       fetch_hourly — agent.blocks.running.fetch_hourly — per phase11's idiom.)
     * R2 fetcher retry loop: patch the low-level requests.get inside
       agent.fetchers.weather so it fails twice then succeeds → fetch_hourly
       retries and returns data (proves with_retries is wired in).
     * R3 dispatch retry loop: patch requests.post inside agent.dispatch.telegram
       so it fails twice then succeeds → send_telegram returns (True, None).

  2. LOGGING (item A)
     Drive agent.main twice (evening + morning) in --dry-run with mocked block
     builders, then assert logs/YYYY-MM.log and logs/messages/*.txt were written
     with the expected structure.

  3. RECIPIENT-SKIP
     With the baby block None (e.g. a non-crèche day), Liliana (baby_only) must
     be skipped while Pawel (full) still receives the digest.

No real dispatch happens (dry-run) and no live APIs are required — everything is
mocked, so this runs anywhere, deterministically.

Run:
  python phase13_test.py
"""

import contextlib
import datetime
import io
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Dummy recipient secrets so dry-run dispatch reports "dry-run", not "missing env".
for _k in ("RECIPIENT_PAWEL_EMAIL", "RECIPIENT_PAWEL_TELEGRAM",
           "RECIPIENT_LILIANA_EMAIL", "RECIPIENT_LILIANA_TELEGRAM"):
    os.environ.setdefault(_k, f"dummy-{_k.lower()}")


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Canned block builders (no network / no LLM) — used for logging + skip tests
# ---------------------------------------------------------------------------

def _slot(t, temp, rain=20, wind=3.0, cloud="Partially sunny"):
    return {"time": t, "temp_c": temp, "wind_ms": wind, "wind_dir": "NE",
            "rain_pct": rain, "cloud_label": cloud}


def _canned(name):
    blocks = {
        "baby": {
            "location": {"city": "Winterthur", "postcode": 8400},
            "baby_age_months": 4,
            "drop_off": _slot("08:00", 9.0, rain=30),
            "pick_up":  _slot("16:15", 14.0, rain=10),
            "alerts": [], "clothing": {"outfit": "fleece suit",
                                       "pushchair_extras": "footmuff",
                                       "pick_up_note": ""},
        },
        "cycling": {"location": "Zurich 8001", "date": "Fri 29 May",
                    "slots": [_slot("06:30", 11.0), _slot("16:30", 17.0)],
                    "alerts": [], "clothing": {"wear": "jersey", "pack": "shell"}},
        "running": {"location": {"city": "Winterthur", "postcode": 8400},
                    "date": "Fri 29 May", "slot": _slot("07:00", 10.5, rain=35),
                    "alerts": [], "clothing": {"dry": "top + shorts", "wet": "cap",
                                               "wet_active": True}},
        "swimming": {"location": {"city": "Thalwil", "postcode": 8800},
                     "swim_time": "07:00", "water_temp_c": 18.5,
                     "air": _slot("07:00", 12.0)},
        "stocks": {"tickers": [{"ticker": "KRU", "exchange": "WSE",
                                "date": "2026-05-28", "close": 412.5,
                                "change_pct": 1.73, "portfolio_value": 41250.0,
                                "portfolio_change": 700.5, "shares": 100,
                                "currency": "PLN", "error": None}]},
    }
    return blocks[name]


def _patch_builders(M, baby=True):
    """Point agent.main's block builders at canned data. baby=False → None baby."""
    M.build_baby_block     = (lambda cfg, td: _canned("baby")) if baby else (lambda cfg, td: None)
    M.build_cycling_block  = lambda cfg, td: _canned("cycling")
    M.build_running_block  = lambda cfg, td: _canned("running")
    M.build_swimming_block = lambda cfg, td: _canned("swimming")
    M.build_stocks_block   = lambda cfg:     _canned("stocks")


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_retry_paths() -> bool:
    _section("1 — Retry paths")
    ok = True

    # R1 — graceful degradation: consumer-module fetcher always raises.
    import agent.blocks.running as run_mod
    real_fetch  = run_mod.fetch_hourly
    real_alerts = run_mod.fetch_meteoswiss_alerts
    run_mod.fetch_hourly = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("simulated outage"))
    run_mod.fetch_meteoswiss_alerts = lambda *a, **k: []
    try:
        cfg = {
            "cloud_cover_labels": {"Sunny": [0, 20], "Partially sunny": [21, 50],
                                   "Mostly cloudy": [51, 80], "Overcast": [81, 100]},
            "alerts": {"meteoswiss": {"severity_min": 2}},
            "workouts": {"running": {
                "location": {"postcode": 8400, "city": "Winterthur", "lat": 47.5, "lon": 8.7},
                "times": ["07:00"], "wet_threshold_pct": 30,
                "clothing_bands": [{"max_c": 100, "dry": "shorts", "wet": "cap"}]}},
        }
        block = run_mod.build_running_block(cfg, datetime.date(2099, 1, 1))
        if block is None:
            print("  R1 OK: failing fetcher → block None (no crash)")
        else:
            print("  R1 FAIL: expected None block"); ok = False
    finally:
        run_mod.fetch_hourly = real_fetch
        run_mod.fetch_meteoswiss_alerts = real_alerts

    # R2 — fetcher retry loop: requests.get fails twice then succeeds.
    import agent.fetchers.weather as wx
    import agent.retry as R
    real_get, real_sleep = wx.requests.get, R.time.sleep
    R.time.sleep = lambda s: None
    calls = {"n": 0}
    fake_payload = {"hourly": {
        "time": ["2099-01-01T07:00"], "temperature_2m": [8.0],
        "windspeed_10m": [2.0], "winddirection_10m": [45],
        "precipitation_probability": [10], "cloudcover": [30]}}

    def _flaky_get(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise wx.requests.ConnectionError(f"blip {calls['n']}")
        return _FakeResp(fake_payload)
    wx.requests.get = _flaky_get
    try:
        rows = wx.fetch_hourly(latitude=47.5, longitude=8.7)
        if rows and calls["n"] == 3:
            print(f"  R2 OK: fetch_hourly retried {calls['n']}x then returned {len(rows)} row(s)")
        else:
            print(f"  R2 FAIL: calls={calls['n']} rows={rows}"); ok = False
    finally:
        wx.requests.get = real_get
        R.time.sleep = real_sleep

    # R3 — dispatch retry loop: requests.post fails twice then succeeds.
    import agent.dispatch.telegram as tg
    os.environ["TELEGRAM_BOT_TOKEN"] = "dummy-token"
    real_post, real_sleep2 = tg.requests.post, R.time.sleep
    R.time.sleep = lambda s: None
    pcalls = {"n": 0}

    def _flaky_post(*a, **k):
        pcalls["n"] += 1
        if pcalls["n"] < 3:
            raise tg.requests.ConnectionError(f"post blip {pcalls['n']}")
        return _FakeResp({"ok": True})
    tg.requests.post = _flaky_post
    try:
        sent_ok, err = tg.send_telegram(chat_id="123", text="hi")
        if sent_ok and pcalls["n"] == 3:
            print(f"  R3 OK: send_telegram retried {pcalls['n']}x → (True, None)")
        else:
            print(f"  R3 FAIL: ok={sent_ok} err={err} calls={pcalls['n']}"); ok = False
    finally:
        tg.requests.post = real_post
        R.time.sleep = real_sleep2

    return ok


def test_logging() -> bool:
    _section("2 — Logging (evening + morning, dry-run)")
    import agent.main as M
    _patch_builders(M, baby=True)

    month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    log_path = os.path.join("logs", f"{month}.log")
    before = os.path.getsize(log_path) if os.path.exists(log_path) else 0

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M.main(run_type="evening", dry_run=True)
        M.main(run_type="morning", dry_run=True)

    ok = True
    if not (os.path.exists(log_path) and os.path.getsize(log_path) > before):
        print(f"  FAIL: {log_path} not appended to"); ok = False
    else:
        text = open(log_path, encoding="utf-8").read()[before:]
        for marker in ("run=evening", "run=morning", "blocks:", "dispatch:", "result:"):
            if marker not in text:
                print(f"  FAIL: log missing marker {marker!r}"); ok = False
        if ok:
            print(f"  OK: structured entries appended to {log_path}")

    today = datetime.date.today()
    even_msg = os.path.join("logs", "messages", f"{today + datetime.timedelta(days=1)}-evening.txt")
    morn_msg = os.path.join("logs", "messages", f"{today}-morning.txt")
    for p, banner in ((even_msg, "Morning Briefing"), (morn_msg, "Morning Update")):
        if os.path.exists(p) and banner in open(p, encoding="utf-8").read():
            print(f"  OK: archived {os.path.basename(p)} (banner '{banner}')")
        else:
            print(f"  FAIL: {p} missing or wrong banner"); ok = False
    return ok


def test_recipient_skip() -> bool:
    _section("3 — Recipient skip (baby None → Liliana skipped)")
    import agent.main as M
    _patch_builders(M, baby=False)   # non-crèche-style: no baby content

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M.main(run_type="evening", dry_run=True)
    out = buf.getvalue()

    ok = True
    if "skipping — no content for role 'baby_only'" in out:
        print("  OK: Liliana (baby_only) skipped — no baby content")
    else:
        print("  FAIL: Liliana was not skipped"); ok = False
    # Pawel (full) still has cycling/running/etc., so should dispatch.
    if "[Pawel" in out and "DRY-RUN would send" in out:
        print("  OK: Pawel (full) still dispatched")
    else:
        print("  FAIL: Pawel was not dispatched"); ok = False
    return ok


if __name__ == "__main__":
    results = {
        "retry":  test_retry_paths(),
        "logging": test_logging(),
        "skip":    test_recipient_skip(),
    }
    _section("Summary")
    for name, passed in results.items():
        print(f"  {name:<8}: {'PASS' if passed else 'FAIL'}")
    all_ok = all(results.values())
    print(f"\n  Phase 13 test: {'ALL PASS' if all_ok else 'FAILURES PRESENT'}")
    sys.exit(0 if all_ok else 1)
