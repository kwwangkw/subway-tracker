# SPDX-License-Identifier: MIT
# code.py — Main entry point with mode switching
#
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 LED matrices
# Display: 128x32 pixels total
#
# Boots into the last-used mode (saved in /mode.txt).
# Switch modes remotely via http://display.local
#
# This file runs automatically when the MatrixPortal S3 boots.

import time
import os
import gc
import board
import displayio
import rgbmatrix
import framebufferio
import wifi
import socketpool
import microcontroller
from watchdog import WatchDogMode

from train_sign import (
    create_display_group,
    draw_loading_screen,
    draw_no_wifi_screen,
)
import mta_feed
import web_server

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------
BRIGHTNESS = float(os.getenv("MTA_BRIGHTNESS", "0.12"))
MODE_FILE = "/mode.txt"
DEFAULT_MODE = "train"

# ---------------------------------------------------------------
# Display setup — two chained 64x32 HUB75 panels = 128x32
# ---------------------------------------------------------------
displayio.release_displays()

matrix = rgbmatrix.RGBMatrix(
    width=128,
    height=32,
    bit_depth=5,
    rgb_pins=[
        board.MTX_R1, board.MTX_B1, board.MTX_G1,
        board.MTX_R2, board.MTX_B2, board.MTX_G2,
    ],
    addr_pins=[
        board.MTX_ADDRA, board.MTX_ADDRB,
        board.MTX_ADDRC, board.MTX_ADDRD,
    ],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
    tile=1,
    serpentine=True,
)

display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

# ---------------------------------------------------------------
# Create display group and show loading screen
# ---------------------------------------------------------------
group, bitmap, palette = create_display_group(brightness=BRIGHTNESS)
display.root_group = group

draw_loading_screen(bitmap, palette)

# ---------------------------------------------------------------
# Watchdog — auto-reboot if code hangs for > 30 seconds
# ---------------------------------------------------------------
wdt = microcontroller.watchdog
wdt.timeout = 30
wdt.mode = WatchDogMode.RESET
wdt.feed()

# ---------------------------------------------------------------
# Wi-Fi connection
# ---------------------------------------------------------------
print("Connecting to WiFi...")
wdt.feed()
try:
    wifi.radio.connect(
        os.getenv("CIRCUITPY_WIFI_SSID"),
        os.getenv("CIRCUITPY_WIFI_PASSWORD"),
    )
    print(f"Connected! IP: {wifi.radio.ipv4_address}")
except Exception as e:
    print(f"WiFi connection failed: {e}")
    draw_no_wifi_screen(bitmap, palette)
    while True:
        time.sleep(10)
        wdt.feed()
        try:
            wifi.radio.connect(
                os.getenv("CIRCUITPY_WIFI_SSID"),
                os.getenv("CIRCUITPY_WIFI_PASSWORD"),
            )
            print(f"Connected! IP: {wifi.radio.ipv4_address}")
            break
        except Exception:
            pass

# ---------------------------------------------------------------
# NTP time sync (needed for train mode)
# ---------------------------------------------------------------
pool = socketpool.SocketPool(wifi.radio)

print("Syncing time via NTP...")
wdt.feed()
try:
    _ntp_buf = bytearray(48)
    _ntp_buf[0] = 0x1B
    _ntp_sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    _ntp_sock.settimeout(5)
    _ntp_sock.sendto(_ntp_buf, ("pool.ntp.org", 123))
    _ntp_sock.recvfrom_into(_ntp_buf)
    _ntp_sock.close()
    _ntp_secs = (
        _ntp_buf[40] << 24 | _ntp_buf[41] << 16 |
        _ntp_buf[42] << 8  | _ntp_buf[43]
    )
    _ntp_unix = _ntp_secs - 2208988800
    _boot_time = time.time()
    mta_feed.EPOCH_OFFSET = _ntp_unix - _boot_time
    print(f"Time synced! offset={mta_feed.EPOCH_OFFSET}")
    del _ntp_buf, _ntp_secs, _ntp_unix, _boot_time
except Exception as e:
    print(f"NTP sync failed: {e}")

gc.collect()

# ---------------------------------------------------------------
# Mode persistence
# ---------------------------------------------------------------
def _load_mode():
    try:
        with open(MODE_FILE, "r") as f:
            mode = f.read().strip()
            if mode:
                return mode
    except Exception:
        pass
    return DEFAULT_MODE


def _save_mode(mode):
    try:
        with open(MODE_FILE, "w") as f:
            f.write(mode)
    except Exception as e:
        print(f"Could not save mode: {e}")


# ---------------------------------------------------------------
# Mode loading
# ---------------------------------------------------------------
def _load_mode_module(mode_name):
    """Import and return the mode module. Returns None on failure."""
    gc.collect()
    try:
        if mode_name == "train":
            from modes import train
            return train
        elif mode_name == "halloween":
            from modes import halloween
            return halloween
        elif mode_name == "christmas":
            from modes import christmas
            return christmas
        elif mode_name == "thanksgiving":
            from modes import thanksgiving
            return thanksgiving
        elif mode_name == "july4th":
            from modes import july4th
            return july4th
        elif mode_name == "newyear":
            from modes import newyear
            return newyear
        elif mode_name == "valentines":
            from modes import valentines
            return valentines
        elif mode_name == "stpatricks":
            from modes import stpatricks
            return stpatricks
        elif mode_name == "beachday":
            from modes import beachday
            return beachday
        elif mode_name == "clock":
            from modes import clock
            return clock
        elif mode_name == "weather":
            from modes import weather
            return weather
        elif mode_name == "stocks":
            from modes import stocks
            return stocks
        else:
            print(f"Unknown mode: {mode_name}")
            return None
    except Exception as e:
        print(f"Failed to load mode {mode_name}: {e}")
        return None


def _clear_bitmap():
    """Clear the entire display."""
    for y in range(32):
        for x in range(128):
            bitmap[x, y] = 0


def _activate_mode(mode_name):
    """Load a mode module, clear display, call setup(). Returns module."""
    print(f"Activating mode: {mode_name}")
    mod = _load_mode_module(mode_name)
    if mod is None:
        # Fallback to train
        if mode_name != "train":
            print("Falling back to train mode")
            mod = _load_mode_module("train")
            mode_name = "train"
    if mod is None:
        return None

    _clear_bitmap()
    wdt.feed()

    # Train and weather modes need pool for HTTP; others don't
    if mode_name in ("train", "weather", "stocks"):
        mod.setup(bitmap, palette, pool=pool)
    else:
        mod.setup(bitmap, palette)

    # If activating weather, push current zip from web_server
    if mode_name == "weather":
        mod.update_config(zip_code=web_server._zip_code)

    # If activating stocks, push current symbols from web_server
    if mode_name == "stocks":
        mod.update_config(symbols=web_server._stock_symbols)

    # If activating clock and we have a detected timezone, push it
    if mode_name == "clock" and _detected_tz is not None:
        mod.update_timezone(_detected_tz)

    gc.collect()
    return mod


# ---------------------------------------------------------------
# Start HTTP server for mode switching
# ---------------------------------------------------------------
web_server.start(pool)

# Auto-detected timezone from weather API (shared between clock/weather)
_detected_tz = None

# ---------------------------------------------------------------
# Holiday auto-detect
# ---------------------------------------------------------------
def _get_holiday_mode():
    """Check if today is a holiday and return the matching mode name.

    Uses NTP-synced time. Returns None if not a holiday.
    """
    try:
        now = time.localtime(time.time() + mta_feed.EPOCH_OFFSET)
        month = now.tm_mon
        day = now.tm_mday

        # Fixed-date holidays
        if month == 1 and day == 1:
            return "newyear"
        if month == 2 and day == 14:
            return "valentines"
        if month == 3 and day == 17:
            return "stpatricks"
        if month == 7 and day == 4:
            return "july4th"
        if month == 10 and day == 31:
            return "halloween"
        if month == 12 and day == 25:
            return "christmas"

        # Thanksgiving — 4th Thursday of November
        if month == 11:
            # Find the 4th Thursday: weekday 3 (Mon=0)
            # tm_wday: 0=Monday ... 6=Sunday
            # Count Thursdays up to today
            count = 0
            for d in range(1, day + 1):
                # day-of-week for Nov d: shift from day 1's weekday
                t = time.localtime(time.mktime((now.tm_year, 11, d, 0, 0, 0, 0, 0, -1)))
                if t.tm_wday == 3:  # Thursday
                    count += 1
                    if count == 4 and d == day:
                        return "thanksgiving"
    except Exception as e:
        print(f"Holiday check failed: {e}")
    return None


# ---------------------------------------------------------------
# Load initial mode
# ---------------------------------------------------------------
# Check for holiday override first, then fall back to saved mode
_holiday_mode = _get_holiday_mode()
if _holiday_mode:
    current_mode_name = _holiday_mode
    print(f"Holiday detected! Using mode: {current_mode_name}")
else:
    current_mode_name = _load_mode()
print(f"Boot mode: {current_mode_name}")
current_module = _activate_mode(current_mode_name)

# Track whether user manually switched mode (skip holiday auto-switch)
_user_switched = False
_last_holiday_check_day = -1

# ---------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------
while True:
    wdt.feed()

    # Daily holiday check — auto-switch at midnight rollover
    if not _user_switched:
        try:
            _now_t = time.localtime(time.time() + mta_feed.EPOCH_OFFSET)
            _today = _now_t.tm_mday
            if _today != _last_holiday_check_day:
                _last_holiday_check_day = _today
                _user_switched = False  # reset daily — give holiday a chance
                _hm = _get_holiday_mode()
                if _hm and _hm != current_mode_name:
                    print(f"Holiday auto-switch: {current_mode_name} -> {_hm}")
                    import sys
                    old_key = f"modes.{current_mode_name}"
                    if old_key in sys.modules:
                        del sys.modules[old_key]
                    gc.collect()
                    current_mode_name = _hm
                    current_module = _activate_mode(current_mode_name)
        except Exception:
            pass

    # Check for mode switch or stop change via HTTP
    action = web_server.poll(current_mode_name)
    if action is not None:
        # Handle settings change
        if "settings" in action:
            s = action["settings"]
            if "stops" in s:
                if current_mode_name == "train" and current_module is not None:
                    current_module.update_stops(s["stops"])
            if "zip" in s:
                # Try to push to weather module if it's loaded
                import sys
                if "modes.weather" in sys.modules:
                    sys.modules["modes.weather"].update_config(zip_code=s["zip"])
            if "symbols" in s:
                import sys
                if "modes.stocks" in sys.modules:
                    sys.modules["modes.stocks"].update_config(symbols=s["symbols"])

        # Handle mode switch
        new_mode = action.get("mode")
        if new_mode is not None and new_mode != current_mode_name:
            print(f"Mode switch: {current_mode_name} -> {new_mode}")
            _user_switched = True  # user took control, skip holiday auto-switch

            # Unload old module from sys.modules to free RAM
            import sys
            old_key = f"modes.{current_mode_name}"
            if old_key in sys.modules:
                del sys.modules[old_key]
            gc.collect()

            current_mode_name = new_mode
            _save_mode(current_mode_name)
            current_module = _activate_mode(current_mode_name)

    # Run one animation step
    if current_module is not None:
        try:
            sleep_time = current_module.animate(bitmap)
        except Exception as e:
            print(f"Animate error: {e}")
            sleep_time = 1.0

        # Sync auto-detected timezone from weather module
        if current_mode_name == "weather":
            tz = current_module.get_tz_offset()
            if tz is not None and tz != _detected_tz:
                _detected_tz = tz
                print(f"Auto-detected timezone: UTC{tz:+d}")
    else:
        sleep_time = 1.0

    time.sleep(sleep_time)
