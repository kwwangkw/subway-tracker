# SPDX-License-Identifier: MIT
# code.py — Main entry point for the NYC Subway Train Sign
#
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 LED matrices
# Display: 128x32 pixels total
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
import ssl
import microcontroller
import adafruit_requests
from watchdog import WatchDogMode

from train_sign import (
    create_display_group,
    update_display,
    update_display_static,
    update_display_scroll,
    update_time_only,
    needs_scroll,
    draw_loading_screen,
    draw_loading_dots,
    draw_error_screen,
    draw_no_wifi_screen,
)
import mta_feed
from mta_feed import fetch_arrivals_multi, _now_unix

# ---------------------------------------------------------------
# Configuration (from settings.toml)
# ---------------------------------------------------------------
REFRESH_INTERVAL = int(os.getenv("MTA_REFRESH_INTERVAL", "30"))
NUM_ROWS = int(os.getenv("MTA_NUM_ROWS", "2"))
BRIGHTNESS = float(os.getenv("MTA_BRIGHTNESS", "0.12"))

# Per-stop config: comma-separated "stop_id:line:direction" entries
# e.g. MTA_STOPS="721:7:S,G29:G:N"
STOPS_STR = os.getenv("MTA_STOPS", "")

ROW_CONFIGS = [s.strip() for s in STOPS_STR.split(",") if s.strip()]

# ---------------------------------------------------------------
# Display setup — two chained 64x32 HUB75 panels = 128x32
# ---------------------------------------------------------------
displayio.release_displays()

# MatrixPortal S3 pin definitions
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

dots_x, dots_y = draw_loading_screen(bitmap, palette)
_dot_count = 0

def _animate_dots():
    """Advance the loading dots animation by one step."""
    global _dot_count
    _dot_count = (_dot_count % 3) + 1
    draw_loading_dots(bitmap, dots_x, dots_y, _dot_count)
    time.sleep(0.4)

# Animate dots during startup
for _ in range(6):
    _animate_dots()

# ---------------------------------------------------------------
# Watchdog — auto-reboot if code hangs for > 30 seconds
# ---------------------------------------------------------------
wdt = microcontroller.watchdog
wdt.timeout = 30  # seconds
wdt.mode = WatchDogMode.RESET
wdt.feed()  # start the countdown

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
    # Keep animating dots while fetching first data
    for _ in range(3):
        _animate_dots()
except Exception as e:
    print(f"WiFi connection failed: {e}")
    draw_no_wifi_screen(bitmap, palette)
    # Retry loop
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
# NTP time sync — board starts at Jan 1, 2000; we need real time
# to compare against MTA feed Unix timestamps.
# ---------------------------------------------------------------
pool = socketpool.SocketPool(wifi.radio)

print("Syncing time via NTP...")
wdt.feed()
try:
    # Raw NTP query — no extra library needed
    _ntp_buf = bytearray(48)
    _ntp_buf[0] = 0x1B  # NTP version 3, client mode
    _ntp_sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    _ntp_sock.settimeout(5)
    _ntp_sock.sendto(_ntp_buf, ("pool.ntp.org", 123))
    _ntp_sock.recvfrom_into(_ntp_buf)
    _ntp_sock.close()
    # Extract transmit timestamp (bytes 40-43 = seconds since 1900)
    _ntp_secs = (
        _ntp_buf[40] << 24 | _ntp_buf[41] << 16 |
        _ntp_buf[42] << 8  | _ntp_buf[43]
    )
    # Convert NTP epoch (1900) to Unix epoch (1970): subtract 70 years
    _ntp_unix = _ntp_secs - 2208988800
    # Calculate what time.time() *should* be vs what it *is*
    # and store the offset so _now_unix() can use it
    _boot_time = time.time()  # CircuitPython Y2K seconds (small number)
    mta_feed.EPOCH_OFFSET = _ntp_unix - _boot_time
    print(f"Time synced! NTP unix={_ntp_unix}, offset={mta_feed.EPOCH_OFFSET}")
    del _ntp_buf, _ntp_secs, _ntp_unix, _boot_time
except Exception as e:
    print(f"NTP sync failed: {e}")
    # Without accurate time, arrivals will be wrong but we'll try anyway

# ---------------------------------------------------------------
# HTTP session setup
# ---------------------------------------------------------------
ssl_context = ssl.create_default_context()
requests = adafruit_requests.Session(pool, ssl_context)

gc.collect()

# ---------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------
if ROW_CONFIGS:
    print(f"Monitoring: {ROW_CONFIGS}")
else:
    print("WARNING: No stops configured! Set MTA_ROW1/MTA_ROW2 in settings.toml")
print(f"Refresh interval: {REFRESH_INTERVAL}s")

last_fetch = 0
arrivals = []
scroll_maxes = [0, 0]   # scroll wrap distance per row (0 = static)
scroll_offsets = [0, 0]  # current scroll position per row
any_scrolling = False
empty_count = 0          # consecutive fetches with 0 arrivals
MAX_EMPTY = 3            # show "No trains" only after this many empty fetches

SCROLL_SPEED = 1     # pixels per scroll tick
SCROLL_INTERVAL = 0.08  # seconds between scroll frames
MINUTES_INTERVAL = 10   # seconds between minutes recalc
PAUSE_FRAMES = 50       # pause this many frames when text is left-aligned

last_scroll = 0
last_minutes = 0
pause_counters = [0, 0]  # per-row pause counters


def _arrivals_changed(old, new):
    """Check if arrivals have meaningfully changed (different train or time)."""
    if len(old) != len(new):
        return True
    for a, b in zip(old, new):
        if a["route_id"] != b["route_id"]:
            return True
        if a["arrival_time"] != b["arrival_time"]:
            return True
    return False


def _destinations_changed(old, new):
    """Check if destination text changed (requires scroll reset)."""
    if len(old) != len(new):
        return True
    for a, b in zip(old, new):
        if a["destination"] != b["destination"]:
            return True
    return False


fetch_due = True  # fetch immediately on boot

def _scroll_at_pause():
    """True if all scrolling rows are left-aligned and paused."""
    for i in range(len(scroll_maxes)):
        if scroll_maxes[i] > 0 and (scroll_offsets[i] != 0 or pause_counters[i] <= 0):
            return False
    return True

while True:
    now = time.monotonic()
    wdt.feed()  # pet the watchdog every loop

    # --- Fetch new data ---
    if now - last_fetch >= REFRESH_INTERVAL:
        fetch_due = True

    # Only fetch when scroll is at rest (left-aligned pause) to avoid stutter
    if fetch_due and (not any_scrolling or _scroll_at_pause()):
        fetch_due = False
        last_fetch = now
        last_minutes = now
        gc.collect()
        print(f"Fetching arrivals... (free mem: {gc.mem_free()})")

        try:
            new_arrivals = fetch_arrivals_multi(requests, ROW_CONFIGS, NUM_ROWS)
            print(f"Got {len(new_arrivals)} arrivals:")
            for a in new_arrivals:
                print(f"  {a['route_id']} -> {a['destination']} in {a['minutes']}min")

            if new_arrivals:
                empty_count = 0
                if _arrivals_changed(arrivals, new_arrivals):
                    dest_changed = _destinations_changed(arrivals, new_arrivals)
                    arrivals = new_arrivals
                    if dest_changed:
                        # Destination text changed — reset scroll
                        scroll_maxes = [0, 0]
                        scroll_offsets = [0, 0]
                        pause_counters = [0, 0]
                        for i, a in enumerate(arrivals[:2]):
                            scroll_maxes[i] = needs_scroll(a["destination"])
                        any_scrolling = any(s > 0 for s in scroll_maxes)
                        update_display_static(bitmap, palette, arrivals)
                        if any_scrolling:
                            pause_counters = [PAUSE_FRAMES, PAUSE_FRAMES]
                            update_display_scroll(bitmap, arrivals, scroll_offsets, scroll_maxes)
                    else:
                        # Same destinations, just time changed — update time only
                        arrivals = new_arrivals
                        update_time_only(bitmap, arrivals)
                else:
                    print("  (no change, skipping redraw)")
            else:
                empty_count += 1
                print(f"  (empty #{empty_count}/{MAX_EMPTY})")
                if arrivals:
                    # Keep showing old data, just update minutes
                    current_time = _now_unix()
                    for a in arrivals:
                        a["minutes"] = max(0, int((a["arrival_time"] - current_time) / 60))
                    # If all displayed trains are now past, clear them
                    if all(a["minutes"] <= 0 and (a["arrival_time"] < current_time - 60) for a in arrivals):
                        arrivals = []
                        any_scrolling = False
                        draw_error_screen(bitmap, palette, "No trains")
                elif empty_count >= MAX_EMPTY:
                    draw_error_screen(bitmap, palette, "No trains")

        except Exception as e:
            print(f"Fetch error: {e}")
            # Keep current display on fetch errors — don't wipe it
            if not arrivals:
                draw_error_screen(bitmap, palette, "Fetch err")
            try:
                if not wifi.radio.connected:
                    wifi.radio.connect(
                        os.getenv("CIRCUITPY_WIFI_SSID"),
                        os.getenv("CIRCUITPY_WIFI_PASSWORD"),
                    )
            except Exception:
                pass

        gc.collect()  # free HTTP response memory after each fetch

    # --- Scroll animation ---
    if any_scrolling and arrivals and (now - last_scroll) >= SCROLL_INTERVAL:
        last_scroll = now
        for i in range(len(scroll_maxes)):
            if scroll_maxes[i] > 0:
                if pause_counters[i] > 0:
                    pause_counters[i] -= 1
                else:
                    scroll_offsets[i] = (scroll_offsets[i] + SCROLL_SPEED) % scroll_maxes[i]
                    if scroll_offsets[i] == 0:
                        pause_counters[i] = PAUSE_FRAMES
        # Always draw scroll frame — keeps text visible during pause
        update_display_scroll(bitmap, arrivals, scroll_offsets, scroll_maxes)

    # --- Update minutes between fetches ---
    elif arrivals and (now - last_minutes) >= MINUTES_INTERVAL:
        last_minutes = now
        current_time = _now_unix()
        for a in arrivals:
            a["minutes"] = max(0, int((a["arrival_time"] - current_time) / 60))
        update_time_only(bitmap, arrivals)

    time.sleep(0.05 if any_scrolling else 1)
