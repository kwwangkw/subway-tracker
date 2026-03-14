# SPDX-License-Identifier: MIT
# Created by Kevin Wang - https://github.com/kwwangkw/
# code.py - Main entry point with mode switching
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
# Display setup - two chained 64x32 HUB75 panels = 128x32
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

# Peek at saved mode from NVM before WiFi (no network needed)
def _peek_nvm_mode():
    try:
        nvm = microcontroller.nvm
        if nvm[0:2] != b"SS":
            return None
        end = 2
        while end < len(nvm) and nvm[end] != 0:
            end += 1
        raw = bytes(nvm[2:end]).decode("utf-8")
        for line in raw.split("\n"):
            if line.startswith("mode="):
                return line[5:]
    except Exception:
        pass
    return None

_boot_mode = _peek_nvm_mode() or DEFAULT_MODE
draw_loading_screen(bitmap, palette, mode=_boot_mode)

# ---------------------------------------------------------------
# Watchdog - auto-reboot if code hangs for > 30 seconds
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

NTP_RESYNC_INTERVAL = 6 * 3600  # re-sync every 6 hours
_last_ntp_sync = 0

def _ntp_sync():
    """Sync time via NTP. Updates EPOCH_OFFSET."""
    global _last_ntp_sync
    try:
        buf = bytearray(48)
        buf[0] = 0x1B
        sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
        sock.settimeout(5)
        sock.sendto(buf, ("pool.ntp.org", 123))
        sock.recvfrom_into(buf)
        sock.close()
        ntp_secs = (
            buf[40] << 24 | buf[41] << 16 |
            buf[42] << 8  | buf[43]
        )
        ntp_unix = ntp_secs - 2208988800
        mta_feed.EPOCH_OFFSET = ntp_unix - time.time()
        _last_ntp_sync = time.monotonic()
        print(f"Time synced! offset={mta_feed.EPOCH_OFFSET}")
    except Exception as e:
        print(f"NTP sync failed: {e}")

print("Syncing time via NTP...")
wdt.feed()
_ntp_sync()

gc.collect()

# ---------------------------------------------------------------
# Mode persistence
# ---------------------------------------------------------------
def _load_mode():
    saved = web_server.load_mode()
    if saved:
        return saved
    return DEFAULT_MODE


def _save_mode(mode):
    web_server.save_mode(mode)


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
        elif mode_name == "birthday":
            from modes import birthday
            return birthday
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


def _fetch_tz_for_zip(zip_code):
    """Quick timezone lookup for a US zip code via Open-Meteo.

    Returns UTC offset in hours, or None on failure.
    """
    try:
        import ssl
        import adafruit_requests
        ssl_ctx = ssl.create_default_context()
        req = adafruit_requests.Session(pool, ssl_ctx)
        # Geocode
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={zip_code}&count=1&language=en&format=json&country=US"
        resp = req.get(url)
        data = resp.json()
        resp.close()
        if "results" not in data or not data["results"]:
            return None
        lat = data["results"][0]["latitude"]
        lon = data["results"][0]["longitude"]
        # Fetch timezone
        url2 = (f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m&timezone=auto&forecast_days=1")
        resp2 = req.get(url2)
        data2 = resp2.json()
        resp2.close()
        utc_off = data2.get("utc_offset_seconds")
        if utc_off is not None:
            tz = utc_off // 3600
            print(f"Timezone for ZIP {zip_code}: UTC{tz:+d}")
            return tz
    except Exception as e:
        print(f"Timezone fetch failed: {e}")
    return None


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
    elif mode_name == "birthday":
        bd_name = _get_birthday_name()
        mod.setup(bitmap, palette, name=bd_name)
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
def _unix_to_date(unix_ts):
    """Convert Unix timestamp to local (year, month, day) using timezone."""
    tz = _detected_tz if _detected_tz is not None else int(os.getenv("CLOCK_TZ_OFFSET", "-5"))
    ts = unix_ts + tz * 3600
    days = ts // 86400
    y = 1970
    while True:
        leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
        diy = 366 if leap else 365
        if days < diy:
            break
        days -= diy
        y += 1
    leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
    mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    m = 0
    while m < 12 and days >= mdays[m]:
        days -= mdays[m]
        m += 1
    return y, m + 1, days + 1


def _get_birthday_name():
    """Check if today matches any configured birthday.

    Parses BIRTHDAYS from web_server (Name:MM-DD,Name:MM-DD).
    Returns the name if today is a match, or None.
    """
    try:
        bd_str = web_server._birthdays
        if not bd_str:
            return None
        now_unix = time.time() + mta_feed.EPOCH_OFFSET
        _, month, day = _unix_to_date(now_unix)
        for entry in bd_str.split(","):
            entry = entry.strip()
            if ":" not in entry:
                continue
            name, date_str = entry.split(":", 1)
            name = name.strip()
            date_str = date_str.strip()
            if "-" not in date_str:
                continue
            parts = date_str.split("-")
            if len(parts) == 2:
                try:
                    m = int(parts[0])
                    d = int(parts[1])
                    if m == month and d == day:
                        return name
                except ValueError:
                    pass
    except Exception as e:
        print(f"Birthday check failed: {e}")
    return None


def _get_holiday_mode():
    """Check if today is a holiday and return the matching mode name.

    Uses NTP-synced time. Returns None if not a holiday.
    """
    try:
        now_unix = time.time() + mta_feed.EPOCH_OFFSET
        year, month, day = _unix_to_date(now_unix)

        # Birthday check first
        bd_name = _get_birthday_name()
        if bd_name:
            return "birthday"

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

        # Thanksgiving - 4th Thursday of November
        if month == 11:
            # Weekday of Nov 1 using days since Unix epoch
            # Jan 1 1970 = Thursday (3), 0=Mon..6=Sun
            mdays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
            if leap:
                mdays[1] = 29
            d_since = 0
            for y in range(1970, year):
                lp = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
                d_since += 366 if lp else 365
            for mi in range(10):  # Jan..Oct
                d_since += mdays[mi]
            # d_since is now days from epoch to Nov 1
            nov1_wday = (d_since + 3) % 7  # 0=Mon..6=Sun, Thu=3
            # Find 4th Thursday
            # First Thursday: if nov1 is Thu(3), it's day 1; else offset
            first_thu = (3 - nov1_wday) % 7 + 1  # day of month
            fourth_thu = first_thu + 21
            if day == fourth_thu:
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

# Holiday modes that can be auto-switched
_HOLIDAY_MODES = {"newyear", "valentines", "stpatricks", "july4th",
                  "halloween", "thanksgiving", "christmas", "birthday"}

# Track last checked day for holiday revert
_last_holiday_check_day = -1

# ---------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------
while True:
    wdt.feed()

    # Periodic NTP re-sync to prevent clock drift
    if time.monotonic() - _last_ntp_sync >= NTP_RESYNC_INTERVAL:
        _ntp_sync()

    # Daily check - if we're still on a holiday mode after the holiday, revert
    try:
        _now_unix = time.time() + mta_feed.EPOCH_OFFSET
        _, _, _today = _unix_to_date(_now_unix)
        if _today != _last_holiday_check_day:
            _last_holiday_check_day = _today
            if current_mode_name in _HOLIDAY_MODES and _get_holiday_mode() != current_mode_name:
                saved = _load_mode()
                if saved not in _HOLIDAY_MODES:
                    print(f"Holiday over, reverting: {current_mode_name} -> {saved}")
                    import sys
                    old_key = f"modes.{current_mode_name}"
                    if old_key in sys.modules:
                        del sys.modules[old_key]
                    gc.collect()
                    current_mode_name = saved
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
                if current_mode_name == "weather" and current_module is not None:
                    current_module.update_config(zip_code=s["zip"])
                if current_mode_name == "clock" and current_module is not None:
                    # Fetch timezone for the new zip via Open-Meteo
                    _tz = _fetch_tz_for_zip(s["zip"])
                    if _tz is not None:
                        _detected_tz = _tz
                        current_module.update_timezone(_tz)
            if "symbols" in s:
                if current_mode_name == "stocks" and current_module is not None:
                    current_module.update_config(symbols=s["symbols"])
            if "birthdays" in s:
                # If currently in birthday mode, reactivate with new name
                if current_mode_name == "birthday" and current_module is not None:
                    bd_name = _get_birthday_name()
                    if bd_name:
                        current_module.setup(bitmap, palette, name=bd_name)
                    else:
                        # No birthday today anymore, revert
                        saved = _load_mode()
                        if saved not in _HOLIDAY_MODES:
                            print(f"No birthday today, reverting to {saved}")
                            import sys
                            old_key = "modes.birthday"
                            if old_key in sys.modules:
                                del sys.modules[old_key]
                            gc.collect()
                            current_mode_name = saved
                            current_module = _activate_mode(current_mode_name)

        # Handle mode switch
        new_mode = action.get("mode")
        if new_mode is not None and new_mode != current_mode_name:
            print(f"Mode switch: {current_mode_name} -> {new_mode}")

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
