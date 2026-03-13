# Created by Kevin Wang - https://github.com/kwwangkw/
# modes/weather.py - Weather display mode
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
_last_minute = -1  # track displayed minute for time updates
_time_only_update = False  # True when only the clock changed, not weather data
_prev_bottom_str = None  # previously drawn bottom text for incremental clear
_prev_bottom_x = 0
_prev_time_only = None   # previously drawn time_only text (when bottom bar is too wide)
_prev_time_only_x = 0
_lat = None
_lon = None
_location = ""
_fetch_error = False
_tz_offset = None      # auto-detected from API (hours)
_is_day = True         # day/night from API

# --- Previous-draw state for incremental redraw ---
_drawn_temp_str = None   # e.g. "37"
_drawn_temp_end_x = 0    # x after last large digit (for degree/F)
_drawn_icon_key = None   # (icon_id, icon_color) tuple
_drawn_hi_str = None
_drawn_lo_str = None
_drawn_loading = False   # True if loading screen is currently shown

# WMO weather codes -> description and icon type
WMO_CODES = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Lt Frz Drizzle",
    57: "Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Lt Frz Rain",
    67: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Lt Snow Showers",
    86: "Snow Showers",
    95: "Thunderstorm",
    96: "Lt T-storm w/ Hail",
    99: "T-storm w/ Hail",
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


def _clear_rect(x, y, w, h):
    """Clear a rectangular region to black."""
    for py in range(y, y + h):
        for px in range(x, x + w):
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                _bitmap[px, py] = 0


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


def _large_char_width(ch):
    """Return the pixel width of a single large (2x) character."""
    from font_data import FONT_5x7
    glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
    if glyph is None:
        return 6
    return len(glyph) * 2 + 2


def _measure_large_text(text):
    """Measure total width of large (2x) text."""
    return sum(_large_char_width(ch) for ch in text)


def _draw_large_char(x, y, ch, color):
    """Draw one large (2x) character at (x, y). Returns width consumed."""
    from font_data import FONT_5x7
    glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
    if glyph is None:
        return 6
    w = len(glyph)
    for col_i in range(w):
        col_byte = glyph[col_i]
        for row_i in range(7):
            if col_byte & (1 << row_i):
                _set_pixel(x + col_i * 2, y + row_i * 2, color)
                _set_pixel(x + col_i * 2 + 1, y + row_i * 2, color)
                _set_pixel(x + col_i * 2, y + row_i * 2 + 1, color)
                _set_pixel(x + col_i * 2 + 1, y + row_i * 2 + 1, color)
    return w * 2 + 2


def _draw_large_temp(x, y, temp_str, color):
    """Draw temperature in large 5x7 font, double-height."""
    for ch in temp_str:
        x += _draw_large_char(x, y, ch, color)
    return x


def _get_icon_key(code, is_day):
    """Return a comparable key (icon_id, color_index) for the current weather icon."""
    if code is None:
        icon_id = "cloud"
    elif code <= 1:
        icon_id = "sun" if is_day else "moon"
    elif code <= 3:
        icon_id = "cloud"
    elif code <= 48:
        icon_id = "fog"
    elif code <= 57:
        icon_id = "drizzle"
    elif code <= 67:
        icon_id = "rain"
    elif code <= 77:
        icon_id = "snow"
    elif code <= 82:
        icon_id = "showers"
    elif code <= 86:
        icon_id = "snowshowers"
    else:
        icon_id = "thunder"
    # Determine color
    if code is not None and code <= 1:
        color = 4 if is_day else 7
    else:
        color = COLOR_WHITE
    return (icon_id, color)


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
    global _last_minute, _time_only_update, _prev_bottom_str, _prev_bottom_x
    global _prev_time_only, _prev_time_only_x
    global _drawn_temp_str, _drawn_temp_end_x, _drawn_icon_key
    global _drawn_hi_str, _drawn_lo_str, _drawn_loading

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
    _last_minute = -1
    _time_only_update = False
    _prev_bottom_str = None
    _prev_bottom_x = 0
    _prev_time_only = None
    _prev_time_only_x = 0
    _drawn_temp_str = None
    _drawn_temp_end_x = 0
    _drawn_icon_key = None
    _drawn_hi_str = None
    _drawn_lo_str = None
    _drawn_loading = False

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


def _build_bottom_text():
    """Build the bottom bar string (time - condition)."""
    condition = WMO_CODES.get(_weather_code, "Unknown")
    now_unix = time.time() + EPOCH_OFFSET
    tz = _tz_offset if _tz_offset is not None else int(os.getenv("CLOCK_TZ_OFFSET", "-5"))
    ts = now_unix + tz * 3600
    remaining = ts % 86400
    if remaining < 0:
        remaining += 86400
    hh = int(remaining // 3600)
    mm = int((remaining % 3600) // 60)
    ampm = "AM" if hh < 12 else "PM"
    h12 = hh % 12
    if h12 == 0:
        h12 = 12
    time_str = f"{h12}:{mm:02d}{ampm}"
    bottom_str = f"{time_str} - {condition.upper()}"
    bottom_w = _measure_text(bottom_str)
    if bottom_w > WIDTH:
        # Too wide: only show condition in bottom bar, time will be drawn elsewhere
        return condition.upper(), _measure_text(condition.upper()), time_str
    return bottom_str, bottom_w, None


def _char_width(ch):
    """Return pixel width of a single small character (glyph columns)."""
    from font_data import FONT_5x7
    glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
    return len(glyph) if glyph else 4


def _draw_bottom_text():
    """Draw the bottom time/condition bar, clearing old text first."""
    global _prev_bottom_str, _prev_bottom_x
    global _prev_time_only, _prev_time_only_x
    bottom_str, bottom_w, time_only = _build_bottom_text()
    bottom_y = 24
    bottom_x = (WIDTH - bottom_w) // 2

    bottom_changed = bottom_str != _prev_bottom_str or bottom_x != _prev_bottom_x
    time_changed = time_only != _prev_time_only

    if not bottom_changed and not time_changed:
        return  # nothing changed

    # Redraw main bottom bar if changed
    if bottom_changed:
        old_str = _prev_bottom_str or ""
        # Same length & same position: per-character diff (only redraw changed chars)
        if len(old_str) == len(bottom_str) and bottom_x == _prev_bottom_x:
            cx = bottom_x
            for i in range(len(bottom_str)):
                cw = _char_width(bottom_str[i])
                if old_str[i] != bottom_str[i]:
                    _clear_rect(cx, bottom_y, cw + 1, 7)  # +1 for gap
                    _draw_small_text(cx, bottom_y, bottom_str[i], 5)
                cx += cw + 1
        else:
            # Different length or position: full clear + redraw
            if old_str:
                prev_w = _measure_text(old_str)
                _clear_rect(_prev_bottom_x, bottom_y, prev_w, 7)
            _draw_small_text(bottom_x, bottom_y, bottom_str, 5)
        _prev_bottom_str = bottom_str
        _prev_bottom_x = bottom_x

    # Handle separate time text (when condition is too wide for combined string)
    if time_only is not None:
        if time_changed:
            time_x = 12  # same as icon left edge
            # Clear previous time using OLD width
            if _prev_time_only is not None:
                old_time_w = _measure_text(_prev_time_only)
                _clear_rect(_prev_time_only_x, 15, old_time_w, 7)
            _draw_small_text(time_x, 15, time_only, 5)
            _prev_time_only = time_only
            _prev_time_only_x = time_x
    elif _prev_time_only is not None:
        # Condition shortened enough to fit — clear leftover time text
        old_time_w = _measure_text(_prev_time_only)
        _clear_rect(_prev_time_only_x, 15, old_time_w, 7)
        _prev_time_only = None
        _prev_time_only_x = 0


# Layout constants
_ICON_X = 12
_ICON_Y = 3
_ICON_W = 12
_ICON_H = 10
_TEMP_X = 28
_TEMP_Y = 3
_TEMP_LARGE_H = 14  # 7 rows * 2
_HILO_X = 90
_HI_Y = 3
_LO_Y = 12


def animate(bitmap):
    """Update weather display. Returns sleep time."""
    global _last_fetch, _needs_redraw, _last_minute, _time_only_update
    global _drawn_temp_str, _drawn_temp_end_x, _drawn_icon_key
    global _drawn_hi_str, _drawn_lo_str, _drawn_loading
    global _prev_bottom_str, _prev_time_only

    now = time.monotonic()

    # Fetch weather data periodically
    if _requests is not None and (now - _last_fetch >= REFRESH_INTERVAL or _temperature is None):
        _last_fetch = now
        _fetch_weather(_requests)
        _needs_redraw = True
        _time_only_update = False

    # Check if the minute changed - only bottom text needs updating
    now_unix = time.time() + EPOCH_OFFSET
    tz = _tz_offset if _tz_offset is not None else int(os.getenv("CLOCK_TZ_OFFSET", "-5"))
    remaining = (now_unix + tz * 3600) % 86400
    if remaining < 0:
        remaining += 86400
    cur_minute = int((remaining % 3600) // 60)
    if cur_minute != _last_minute:
        _last_minute = cur_minute
        if not _needs_redraw:
            _time_only_update = True
            _needs_redraw = True

    # Nothing to update
    if not _needs_redraw:
        return 0.5
    _needs_redraw = False

    # If only the time changed, just redraw the bottom bar
    if _time_only_update and _temperature is not None:
        _time_only_update = False
        _draw_bottom_text()
        return 0.5
    _time_only_update = False

    # --- Loading state ---
    if _temperature is None:
        if not _drawn_loading:
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    bitmap[x, y] = 0
            load_str = "LOADING..."
            lx = (WIDTH - _measure_text(load_str)) // 2
            _draw_small_text(lx, 12, load_str, COLOR_WHITE)
            _drawn_loading = True
        return 0.5

    # If we were showing loading, clear it once
    if _drawn_loading:
        for y in range(HEIGHT):
            for x in range(WIDTH):
                bitmap[x, y] = 0
        _drawn_loading = False
        # Reset all drawn state so everything draws fresh
        _drawn_temp_str = None
        _drawn_temp_end_x = 0
        _drawn_icon_key = None
        _drawn_hi_str = None
        _drawn_lo_str = None
        _prev_bottom_str = None
        _prev_time_only = None

    # --- Left side: icon (12x12) ---
    new_icon_key = _get_icon_key(_weather_code, _is_day)
    if new_icon_key != _drawn_icon_key:
        # Clear icon area and redraw
        _clear_rect(_ICON_X, _ICON_Y, _ICON_W, _ICON_H)
        icon = _get_icon(_weather_code, _is_day)
        _draw_icon(_ICON_X, _ICON_Y, icon, new_icon_key[1])
        _drawn_icon_key = new_icon_key

    # --- Center: large temperature (per-digit incremental) ---
    temp_int = int(round(_temperature)) if _temperature is not None else 0
    new_temp_str = f"{temp_int}"

    if new_temp_str != _drawn_temp_str:
        old_str = _drawn_temp_str or ""

        # Same length: only redraw changed digits, leave others untouched
        if len(old_str) == len(new_temp_str):
            cx = _TEMP_X
            for i in range(len(new_temp_str)):
                cw = _large_char_width(new_temp_str[i])
                if old_str[i] != new_temp_str[i]:
                    _clear_rect(cx, _TEMP_Y, cw, _TEMP_LARGE_H)
                    _draw_large_char(cx, _TEMP_Y, new_temp_str[i], 3)
                cx += cw
        else:
            # Different length: clear old region, redraw all digits
            old_end = _drawn_temp_end_x + 20 if _drawn_temp_end_x > 0 else _TEMP_X
            _clear_rect(_TEMP_X, _TEMP_Y, old_end - _TEMP_X, _TEMP_LARGE_H)
            _draw_large_temp(_TEMP_X, _TEMP_Y, new_temp_str, 3)

        # Redraw degree symbol and F (position may shift)
        new_end_x = _TEMP_X + _measure_large_text(new_temp_str)
        if new_end_x != _drawn_temp_end_x:
            if _drawn_temp_end_x > 0:
                _clear_rect(_drawn_temp_end_x, _TEMP_Y, 20, 7)
            _set_pixel(new_end_x, 3, 3)
            _set_pixel(new_end_x + 1, 3, 3)
            _set_pixel(new_end_x, 4, 3)
            _set_pixel(new_end_x + 1, 4, 3)
            _draw_small_text(new_end_x + 3, 3, "F", 3)

        _drawn_temp_str = new_temp_str
        _drawn_temp_end_x = new_end_x

    # --- Right side: Hi/Lo ---
    new_hi_str = f"H:{int(round(_temp_high))}" if _temp_high is not None else None
    if new_hi_str != _drawn_hi_str:
        # Clear old
        if _drawn_hi_str is not None:
            old_w = _measure_text(_drawn_hi_str)
            _clear_rect(_HILO_X, _HI_Y, old_w, 7)
        if new_hi_str is not None:
            _draw_small_text(_HILO_X, _HI_Y, new_hi_str, 6)
        _drawn_hi_str = new_hi_str

    new_lo_str = f"L:{int(round(_temp_low))}" if _temp_low is not None else None
    if new_lo_str != _drawn_lo_str:
        # Clear old
        if _drawn_lo_str is not None:
            old_w = _measure_text(_drawn_lo_str)
            _clear_rect(_HILO_X, _LO_Y, old_w, 7)
        if new_lo_str is not None:
            _draw_small_text(_HILO_X, _LO_Y, new_lo_str, 7)
        _drawn_lo_str = new_lo_str

    # --- Bottom: time - conditions text ---
    _draw_bottom_text()

    return 0.5
