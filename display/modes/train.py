# modes/train.py — Train Sign mode wrapper
#
# Wraps the existing TrainSign code into the setup()/animate() interface.
# Unlike holiday modes, this needs WiFi, NTP, and HTTP session.

import time
import os
import gc
import wifi
import ssl
import adafruit_requests

from train_sign import (
    update_display,
    update_display_static,
    update_display_scroll,
    update_time_only,
    needs_scroll,
    draw_loading_screen,
    draw_loading_dots,
    draw_error_screen,
    draw_no_wifi_screen,
    _dim,
    COLOR_BLACK,
    COLOR_WHITE,
    COLOR_DIVIDER,
)
import mta_feed
from mta_feed import fetch_arrivals_multi, _now_unix

# Configuration (from settings.toml)
REFRESH_INTERVAL = int(os.getenv("MTA_REFRESH_INTERVAL", "30"))
NUM_ROWS = int(os.getenv("MTA_NUM_ROWS", "2"))
STOPS_STR = os.getenv("MTA_STOPS", "")
ROW_CONFIGS = [s.strip() for s in STOPS_STR.split(",") if s.strip()]

# State
_bitmap = None
_palette = None
_requests = None

_last_fetch = 0
_arrivals = []
_scroll_maxes = [0, 0]
_scroll_offsets = [0, 0]
_any_scrolling = False
_empty_count = 0
MAX_EMPTY = 3

SCROLL_SPEED = 1
SCROLL_INTERVAL = 0.08
MINUTES_INTERVAL = 10
PAUSE_FRAMES = 50

_last_scroll = 0
_last_minutes = 0
_pause_counters = [0, 0]
_fetch_due = True
_initialized = False


def update_stops(new_configs):
    """Update stop configs at runtime and force a re-fetch."""
    global _fetch_due, _last_fetch, _arrivals, _scroll_maxes, _scroll_offsets
    global _any_scrolling, _pause_counters

    ROW_CONFIGS[:] = new_configs
    _arrivals = []
    _scroll_maxes[:] = [0, 0]
    _scroll_offsets[:] = [0, 0]
    _any_scrolling = False
    _pause_counters[:] = [0, 0]
    _last_fetch = 0
    _fetch_due = True
    print(f"Train stops updated: {ROW_CONFIGS}")

    # Clear display and show loading while re-fetching
    if _bitmap is not None and _palette is not None:
        for y in range(32):
            for x in range(128):
                _bitmap[x, y] = 0
        draw_loading_screen(_bitmap, _palette)


def _arrivals_changed(old, new):
    if len(old) != len(new):
        return True
    for a, b in zip(old, new):
        if a["route_id"] != b["route_id"]:
            return True
        if a["arrival_time"] != b["arrival_time"]:
            return True
    return False


def _destinations_changed(old, new):
    if len(old) != len(new):
        return True
    for a, b in zip(old, new):
        if a["destination"] != b["destination"]:
            return True
    return False


def _scroll_at_pause():
    for i in range(len(_scroll_maxes)):
        if _scroll_maxes[i] > 0 and (_scroll_offsets[i] != 0 or _pause_counters[i] <= 0):
            return False
    return True


def setup(bitmap, palette, pool=None, **kwargs):
    """Initialize train mode. Requires pool (socketpool) kwarg."""
    global _bitmap, _palette, _requests, _initialized
    global _last_fetch, _arrivals, _scroll_maxes, _scroll_offsets
    global _any_scrolling, _empty_count, _last_scroll, _last_minutes
    global _pause_counters, _fetch_due

    _bitmap = bitmap
    _palette = palette

    # Reset state
    _last_fetch = 0
    _arrivals = []
    _scroll_maxes = [0, 0]
    _scroll_offsets = [0, 0]
    _any_scrolling = False
    _empty_count = 0
    _last_scroll = 0
    _last_minutes = 0
    _pause_counters = [0, 0]
    _fetch_due = True

    # Restore palette to train sign colors (holiday modes overwrite these)
    palette[COLOR_BLACK] = 0x000000
    wr, wg, wb = _dim(0xFF, 0xFF, 0xFF)
    palette[COLOR_WHITE] = (wr << 16) | (wg << 8) | wb
    dr, dg, db = _dim(0x28, 0x28, 0x28)
    palette[COLOR_DIVIDER] = (dr << 16) | (dg << 8) | db

    # Clear display
    for y in range(32):
        for x in range(128):
            bitmap[x, y] = 0

    # Show loading screen
    draw_loading_screen(bitmap, palette)

    # Set up HTTP session if we have a pool
    if pool is not None:
        ssl_context = ssl.create_default_context()
        _requests = adafruit_requests.Session(pool, ssl_context)

    if ROW_CONFIGS:
        print(f"Train mode: {ROW_CONFIGS}")
    else:
        print("WARNING: No stops configured")

    _initialized = True
    gc.collect()


def animate(bitmap):
    """Run one iteration of the train sign main loop. Returns sleep time."""
    global _last_fetch, _arrivals, _scroll_maxes, _scroll_offsets
    global _any_scrolling, _empty_count, _last_scroll, _last_minutes
    global _pause_counters, _fetch_due

    if not _initialized or _requests is None:
        return 1.0

    now = time.monotonic()

    # --- Fetch new data ---
    if now - _last_fetch >= REFRESH_INTERVAL:
        _fetch_due = True

    if _fetch_due and (not _any_scrolling or _scroll_at_pause()):
        _fetch_due = False
        _last_fetch = now
        _last_minutes = now
        gc.collect()

        try:
            new_arrivals = fetch_arrivals_multi(_requests, ROW_CONFIGS, NUM_ROWS)

            if new_arrivals:
                _empty_count = 0
                if _arrivals_changed(_arrivals, new_arrivals):
                    dest_changed = _destinations_changed(_arrivals, new_arrivals)
                    _arrivals[:] = new_arrivals
                    if dest_changed:
                        _scroll_maxes[:] = [0, 0]
                        _scroll_offsets[:] = [0, 0]
                        _pause_counters[:] = [0, 0]
                        for i, a in enumerate(_arrivals[:2]):
                            _scroll_maxes[i] = needs_scroll(a["destination"])
                        _any_scrolling = any(s > 0 for s in _scroll_maxes)
                        update_display_static(bitmap, _palette, _arrivals)
                        if _any_scrolling:
                            _pause_counters[:] = [PAUSE_FRAMES, PAUSE_FRAMES]
                            update_display_scroll(bitmap, _arrivals, _scroll_offsets, _scroll_maxes)
                    else:
                        update_time_only(bitmap, _arrivals)
            else:
                _empty_count += 1
                if _arrivals:
                    current_time = _now_unix()
                    for a in _arrivals:
                        a["minutes"] = max(0, int((a["arrival_time"] - current_time) / 60))
                    if all(a["minutes"] <= 0 and (a["arrival_time"] < current_time - 60) for a in _arrivals):
                        _arrivals.clear()
                        _any_scrolling = False
                        draw_error_screen(bitmap, _palette, "No trains")
                elif _empty_count >= MAX_EMPTY:
                    draw_error_screen(bitmap, _palette, "No trains")

        except Exception as e:
            print(f"Fetch error: {e}")
            if not _arrivals:
                draw_error_screen(bitmap, _palette, "Fetch err")
            try:
                if not wifi.radio.connected:
                    wifi.radio.connect(
                        os.getenv("CIRCUITPY_WIFI_SSID"),
                        os.getenv("CIRCUITPY_WIFI_PASSWORD"),
                    )
            except Exception:
                pass

        gc.collect()

    # --- Scroll animation ---
    if _any_scrolling and _arrivals and (now - _last_scroll) >= SCROLL_INTERVAL:
        _last_scroll = now
        for i in range(len(_scroll_maxes)):
            if _scroll_maxes[i] > 0:
                if _pause_counters[i] > 0:
                    _pause_counters[i] -= 1
                else:
                    _scroll_offsets[i] = (_scroll_offsets[i] + SCROLL_SPEED) % _scroll_maxes[i]
                    if _scroll_offsets[i] == 0:
                        _pause_counters[i] = PAUSE_FRAMES
        update_display_scroll(bitmap, _arrivals, _scroll_offsets, _scroll_maxes)

    # --- Update minutes between fetches ---
    elif _arrivals and (now - _last_minutes) >= MINUTES_INTERVAL:
        _last_minutes = now
        current_time = _now_unix()
        for a in _arrivals:
            a["minutes"] = max(0, int((a["arrival_time"] - current_time) / 60))
        update_time_only(bitmap, _arrivals)

    return 0.05 if _any_scrolling else 1.0
