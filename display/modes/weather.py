# modes/weather.py — Weather display mode
#
# Shows current temperature and conditions using Open-Meteo API (free, no key).
# Configure WEATHER_ZIP and CLOCK_TZ_OFFSET in settings.toml.

import time
import os
import gc
import ssl
import adafruit_requests

from train_sign import _dim, COLOR_BLACK, COLOR_WHITE
from mta_feed import EPOCH_OFFSET

WIDTH = 128
HEIGHT = 32

# Configuration
ZIP_CODE = os.getenv("WEATHER_ZIP", "10001")
REFRESH_INTERVAL = 300  # 5 minutes

_bitmap = None
_palette = None
_requests = None

_last_fetch = 0
_temperature = None   # current temp in F
_temp_high = None      # today's high
_temp_low = None       # today's low
_weather_code = None   # WMO weather code
_needs_redraw = True
_lat = None
_lon = None
_location = ""
_fetch_error = False
_tz_offset = None      # auto-detected from API (hours)
_is_day = True         # day/night from API

# WMO weather codes -> description and icon type
WMO_CODES = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Freezing Drizzle",
    57: "Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Freezing Rain",
    67: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Snow Showers",
    86: "Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}

# Icon pixel art (simple 12x12 weather icons)
# Sun
_SUN = [
    "....XX.X....",
    ".....XX.....",
    "..X.XXXX.X..",
    "...XXXXXX...",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "...XXXXXX...",
    "..X.XXXX.X..",
    ".....XX.....",
    "....XX.X....",
]

# Moon (crescent)
_MOON = [
    "....XXXXX...",
    "...XXXXXXX..",
    "..XXXXXXX...",
    ".XXXXXXX....",
    ".XXXXXX.....",
    ".XXXXXX.....",
    ".XXXXXXX....",
    "..XXXXXXX...",
    "...XXXXXXX..",
    "....XXXXX...",
]

# Cloud
_CLOUD = [
    "............",
    "....XXXX....",
    "...XXXXXX...",
    "..XXXXXXXX..",
    ".XXXXXXXXXX.",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    ".XXXXXXXXXX.",
    "............",
    "............",
]

# Rain
_RAIN = [
    "....XXXX....",
    "...XXXXXX...",
    "..XXXXXXXX..",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "............",
    ".X..X..X..X.",
    "..X..X..X...",
    ".X..X..X..X.",
    "............",
]

# Snow
_SNOW = [
    "....XXXX....",
    "...XXXXXX...",
    "..XXXXXXXX..",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "............",
    ".X...X...X..",
    "...X...X....",
    "..X...X...X.",
    "............",
]

# Thunder
_THUNDER = [
    "....XXXX....",
    "...XXXXXX...",
    "XXXXXXXXXXXX",
    "XXXXXXXXXXXX",
    "............",
    "....XX......",
    "...XXXX.....",
    ".....XX.....",
    "....XX......",
    "............",
]


def _get_icon(code, is_day=True):
    """Return icon pixel art for a WMO weather code."""
    if code is None:
        return _CLOUD
    if code <= 1:
        return _SUN if is_day else _MOON
    if code <= 3:
        return _CLOUD
    if code <= 48:
        return _CLOUD  # fog
    if code <= 57:
        return _RAIN   # drizzle
    if code <= 67:
        return _RAIN
    if code <= 77:
        return _SNOW
    if code <= 82:
        return _RAIN   # showers
    if code <= 86:
        return _SNOW   # snow showers
    return _THUNDER


def _set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c


def _draw_small_text(x, y, text, color):
    """Draw text using the 5x7 font."""
    from font_data import FONT_5x7
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            x += 4
            continue
        w = len(glyph)
        for col_i in range(w):
            col_byte = glyph[col_i]
            for row_i in range(7):
                if col_byte & (1 << row_i):
                    _set_pixel(x + col_i, y + row_i, color)
        x += w + 1
    return x


def _measure_text(text):
    """Measure text width in pixels."""
    from font_data import FONT_5x7
    w = 0
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph:
            w += len(glyph) + 1
    return w - 1 if w > 0 else 0


def _draw_icon(x, y, icon, color):
    """Draw a pixel art icon."""
    for row_i, row_str in enumerate(icon):
        for col_i, ch in enumerate(row_str):
            if ch == "X":
                _set_pixel(x + col_i, y + row_i, color)


def _draw_large_temp(x, y, temp_str, color):
    """Draw temperature in large 5x7 font, double-height."""
    from font_data import FONT_5x7
    for ch in temp_str:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            x += 6
            continue
        w = len(glyph)
        for col_i in range(w):
            col_byte = glyph[col_i]
            for row_i in range(7):
                if col_byte & (1 << row_i):
                    # Draw 2x2 pixel blocks
                    _set_pixel(x + col_i * 2, y + row_i * 2, color)
                    _set_pixel(x + col_i * 2 + 1, y + row_i * 2, color)
                    _set_pixel(x + col_i * 2, y + row_i * 2 + 1, color)
                    _set_pixel(x + col_i * 2 + 1, y + row_i * 2 + 1, color)
        x += w * 2 + 2
    return x


def _geocode_zip(requests_session, zip_code):
    """Look up lat/lon from US zip code using Open-Meteo geocoding."""
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={zip_code}&count=1&language=en&format=json&country=US"
    try:
        resp = requests_session.get(url)
        data = resp.json()
        resp.close()
        if "results" in data and data["results"]:
            r = data["results"][0]
            return r["latitude"], r["longitude"], r.get("name", zip_code)
    except Exception as e:
        print(f"Geocode error: {e}")

    # Fallback: NYC
    return 40.7128, -74.0060, "New York"


def _fetch_weather(requests_session):
    """Fetch current weather from Open-Meteo."""
    global _temperature, _temp_high, _temp_low, _weather_code, _fetch_error
    global _lat, _lon, _location, _tz_offset, _is_day

    if _lat is None:
        _lat, _lon, _location = _geocode_zip(requests_session, ZIP_CODE)
        print(f"Weather location: {_location} ({_lat}, {_lon})")

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={_lat}&longitude={_lon}"
        f"&current=temperature_2m,weather_code,is_day"
        f"&daily=temperature_2m_max,temperature_2m_min"
        f"&temperature_unit=fahrenheit"
        f"&timezone=auto&forecast_days=1"
    )

    try:
        resp = requests_session.get(url)
        data = resp.json()
        resp.close()

        current = data.get("current", {})
        _temperature = current.get("temperature_2m")
        _weather_code = current.get("weather_code")
        _is_day = bool(current.get("is_day", 1))

        # Auto-detect timezone from API response
        utc_off = data.get("utc_offset_seconds")
        if utc_off is not None:
            _tz_offset = utc_off // 3600

        daily = data.get("daily", {})
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        _temp_high = highs[0] if highs else None
        _temp_low = lows[0] if lows else None

        _fetch_error = False
        print(f"Weather: {_temperature}F, code={_weather_code}, "
              f"hi={_temp_high} lo={_temp_low}, tz=UTC{_tz_offset:+d}")
    except Exception as e:
        print(f"Weather fetch error: {e}")
        _fetch_error = True

    gc.collect()


def get_tz_offset():
    """Return auto-detected timezone offset in hours, or None if not yet known."""
    return _tz_offset


def update_config(zip_code=None, **kwargs):
    """Update weather config and force a re-fetch."""
    global ZIP_CODE, _lat, _lon, _location, _last_fetch, _tz_offset
    if zip_code is not None and zip_code != ZIP_CODE:
        ZIP_CODE = zip_code
        _lat = None  # force re-geocode
        _lon = None
        _location = ""
        _tz_offset = None
        _last_fetch = 0  # force immediate re-fetch
    print(f"Weather config updated: ZIP={ZIP_CODE}")


def setup(bitmap, palette, pool=None, **kwargs):
    """Initialize weather mode."""
    global _bitmap, _palette, _requests, _last_fetch
    global _temperature, _temp_high, _temp_low, _weather_code
    global _lat, _lon, _location, _fetch_error, _needs_redraw

    _bitmap = bitmap
    _palette = palette
    _last_fetch = 0
    _temperature = None
    _temp_high = None
    _temp_low = None
    _weather_code = None
    _lat = None
    _lon = None
    _location = ""
    _fetch_error = False
    _needs_redraw = True

    # Set up colors
    palette[COLOR_BLACK] = 0x000000
    wr, wg, wb = _dim(0xFF, 0xFF, 0xFF)
    palette[COLOR_WHITE] = (wr << 16) | (wg << 8) | wb

    # Temperature color (warm orange)
    tr, tg, tb = _dim(0xFF, 0xAA, 0x33)
    palette[3] = (tr << 16) | (tg << 8) | tb

    # Icon color (yellow for sun, white-ish for clouds)
    ir, ig, ib = _dim(0xFF, 0xDD, 0x44)
    palette[4] = (ir << 16) | (ig << 8) | ib

    # Dim text (hi/lo, conditions)
    dr, dg, db = _dim(0x88, 0x88, 0x88)
    palette[5] = (dr << 16) | (dg << 8) | db

    # Hi color (red-ish)
    hr, hg, hb = _dim(0xFF, 0x66, 0x44)
    palette[6] = (hr << 16) | (hg << 8) | hb

    # Lo color (blue-ish)
    lr, lg, lb = _dim(0x44, 0x88, 0xFF)
    palette[7] = (lr << 16) | (lg << 8) | lb

    # Clear display
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Set up HTTP session
    if pool is not None:
        ssl_context = ssl.create_default_context()
        _requests = adafruit_requests.Session(pool, ssl_context)

    print(f"Weather mode: ZIP={ZIP_CODE}")


def animate(bitmap):
    """Update weather display. Returns sleep time."""
    global _last_fetch, _needs_redraw

    now = time.monotonic()

    # Fetch weather data periodically
    if _requests is not None and (now - _last_fetch >= REFRESH_INTERVAL or _temperature is None):
        _last_fetch = now
        _fetch_weather(_requests)
        _needs_redraw = True

    # Only redraw when data changed
    if not _needs_redraw:
        return 2.0
    _needs_redraw = False

    # Clear
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    if _temperature is None:
        # Loading state
        _draw_small_text(30, 12, "LOADING...", COLOR_WHITE)
        return 0.5

    # --- Left side: icon (12x12) ---
    icon = _get_icon(_weather_code, _is_day)
    # Yellow for sun, soft blue for moon, white for cloud/rain/snow
    if _weather_code is not None and _weather_code <= 1:
        if _is_day:
            icon_color = 4  # yellow
        else:
            icon_color = 7  # blue (lo color) for moon
    else:
        icon_color = COLOR_WHITE
    _draw_icon(12, 3, icon, icon_color)

    # --- Center: large temperature ---
    temp_int = int(round(_temperature)) if _temperature is not None else 0
    temp_str = f"{temp_int}"
    # Draw large temp starting after icon
    end_x = _draw_large_temp(28, 3, temp_str, 3)

    # Degree symbol (small circle) and F
    _set_pixel(end_x, 3, 3)
    _set_pixel(end_x + 1, 3, 3)
    _set_pixel(end_x, 4, 3)
    _set_pixel(end_x + 1, 4, 3)
    _draw_small_text(end_x + 3, 3, "F", 3)

    # --- Right side: Hi/Lo ---
    right_x = 90

    if _temp_high is not None:
        hi_str = f"H:{int(round(_temp_high))}"
        _draw_small_text(right_x, 3, hi_str, 6)

    if _temp_low is not None:
        lo_str = f"L:{int(round(_temp_low))}"
        _draw_small_text(right_x, 12, lo_str, 7)

    # --- Bottom: time - conditions text ---
    condition = WMO_CODES.get(_weather_code, "Unknown")

    # Build 12-hour time string
    now_unix = time.time() + EPOCH_OFFSET
    tz = _tz_offset if _tz_offset is not None else int(os.getenv("CLOCK_TZ_OFFSET", "-5"))
    local = now_unix + tz * 3600
    hh = int(local // 3600) % 24
    mm = int(local // 60) % 60
    ampm = "AM" if hh < 12 else "PM"
    h12 = hh % 12
    if h12 == 0:
        h12 = 12
    time_str = f"{h12}:{mm:02d}{ampm}"

    bottom_str = f"{time_str} - {condition.upper()}"
    bottom_w = _measure_text(bottom_str)

    # Fall back to just condition if too wide
    if bottom_w > WIDTH:
        bottom_str = condition.upper()
        bottom_w = _measure_text(bottom_str)

    bottom_y = 24
    bottom_x = (WIDTH - bottom_w) // 2
    _draw_small_text(bottom_x, bottom_y, bottom_str, 5)

    return 2.0
