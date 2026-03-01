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
    needs_scroll,
    draw_loading_screen,
    draw_error_screen,
    draw_no_wifi_screen,
)
from mta_feed import fetch_arrivals, fetch_arrivals_multi, parse_row_config, fetch_arrivals_multi

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

draw_loading_screen(bitmap, palette)
time.sleep(1)

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
# HTTP session setup
# ---------------------------------------------------------------
pool = socketpool.SocketPool(wifi.radio)
ssl_context = ssl.create_default_context()
requests = adafruit_requests.Session(pool, ssl_context)

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

SCROLL_SPEED = 1     # pixels per scroll tick
SCROLL_INTERVAL = 0.08  # seconds between scroll frames
MINUTES_INTERVAL = 10   # seconds between minutes recalc
PAUSE_FRAMES = 50       # pause this many frames when text is left-aligned

last_scroll = 0
last_minutes = 0
pause_counters = [0, 0]  # per-row pause counters

while True:
    now = time.monotonic()
    wdt.feed()  # pet the watchdog every loop

    # --- Fetch new data ---
    if now - last_fetch >= REFRESH_INTERVAL or last_fetch == 0:
        last_fetch = now
        last_minutes = now
        gc.collect()
        print(f"Fetching arrivals... (free mem: {gc.mem_free()})")

        try:
            arrivals = fetch_arrivals_multi(requests, ROW_CONFIGS, max_results=NUM_ROWS)
            print(f"Got {len(arrivals)} arrivals:")
            for a in arrivals:
                print(f"  {a['route_id']} → {a['destination']} in {a['minutes']}min")

            if arrivals:
                # Compute scroll needs per row
                scroll_maxes = [0, 0]
                scroll_offsets = [0, 0]
                pause_counters = [0, 0]
                for i, a in enumerate(arrivals[:2]):
                    scroll_maxes[i] = needs_scroll(a["destination"])
                any_scrolling = any(s > 0 for s in scroll_maxes)
                update_display_static(bitmap, palette, arrivals)
            else:
                any_scrolling = False
                draw_error_screen(bitmap, palette, "No trains")

        except Exception as e:
            print(f"Fetch error: {e}")
            any_scrolling = False
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
        update_display_scroll(bitmap, arrivals, scroll_offsets, scroll_maxes)

    # --- Update minutes between fetches ---
    elif arrivals and (now - last_minutes) >= MINUTES_INTERVAL:
        last_minutes = now
        current_time = time.time()
        for a in arrivals:
            a["minutes"] = max(0, int((a["arrival_time"] - current_time) / 60))
        if not any_scrolling:
            update_display_static(bitmap, palette, arrivals)

    time.sleep(0.05 if any_scrolling else 1)
