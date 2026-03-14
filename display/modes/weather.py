# Created by Kevin Wang - https://github.com/kwwangkw/
# modes/weather.py - Weather display mode
#
# Shows current temperature and conditions using Open-Meteo API (free, no key).
# Configure WEATHER_ZIP and CLOCK_TZ_OFFSET in settings.toml.

import time
import os
import gc
import ssl
import random
import adafruit_requests

from train_sign import _dim, COLOR_BLACK, COLOR_WHITE
from mta_feed import EPOCH_OFFSET

WIDTH = 128
HEIGHT = 32

# Configuration
ZIP_CODE = os.getenv("WEATHER_ZIP", "10001")
REFRESH_INTERVAL = 300  # 5 minutes

# --- TEST: Set to a WMO code to force a specific icon, or None for normal ---
# 0=Sun, 2=Cloud, 55=Rain, 73=Snow, 95=Thunder
# Set _TEST_IS_DAY=False for Moon (with code 0)
_TEST_WEATHER_CODE = None
_TEST_IS_DAY = None  # True=day(Sun), False=night(Moon), None=normal

_animated_weather = False  # toggled via web settings

_bitmap = None
_palette = None
_requests = None

_last_fetch = 0
_temperature = None   # current temp in F
_feels_like = None     # apparent/feels-like temp in F
_temp_high = None      # today's high
_temp_low = None       # today's low
_weather_code = None   # WMO weather code
_needs_redraw = True
_last_minute = -1  # track displayed minute for time updates
_prev_bottom_str = None  # previously drawn bottom text for incremental clear
_prev_bottom_x = 0
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
_drawn_feels_str = None  # e.g. "Feels Like 72"
_drawn_loading = False   # True if loading screen is currently shown
_icon_frame = 0          # animation frame counter for weather icon
_next_icon_change = 0    # monotonic time for next icon frame change
_icon_showing_alt = False  # whether showing alternate frame
_star_states = None      # list of (on:bool, next_change:float) per star pixel
_snow_flakes = None      # list of [col, row] for each snowflake pixel

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

# Icon pixel art (simple 12x10 weather icons, 2 frames each for animation)
# Sun - round circle with cardinal rays, rays rotate to diagonals
_SUN = [
    [
        ".....X......",
        "........X...",
        ".X..XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX.X",
        "..XXXXXXXX..",
        "X.XXXXXXXX..",
        "...XXXXXX...",
        "....XXXX..X.",
        "...X........",
        "......X.....",
    ],
    [
        "......X.....",
        "..X......X..",
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "X.XXXXXXXX.X",
        "..XXXXXXXX..",
        "...XXXXXX...",
        "....XXXX....",
        "..X......X..",
        ".....X......",
    ]
]

# Moon - filled crescent (single frame base, stars handled separately)
_MOON = [
    [
        "....XXX.....",
        "..XXX.......",
        "..XX........",
        ".XX.........",
        ".XX.........",
        ".XX......X..",
        ".XXX....XX..",
        "..XXXXXXX...",
        "...XXXXXX...",
        "....XXXX....",
        "............",
    ],
]

# Star pixel offsets within icon grid (col, row) - each twinkles independently
_MOON_STARS = [(6, 2), (4, 4), (7, 5)]

# Cloud - top bump shifts right
_CLOUD = [
    [
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
        "............",
    ],
    [
        "............",
        ".....XXXX...",
        "....XXXXXX..",
        "..XXXXXXXXX.",
        ".XXXXXXXXXX.",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        ".XXXXXXXXXX.",
        "............",
        "............",
        "............",
    ],
]

# Rain - 3 drop columns falling continuously (6 frames)
_RAIN = [
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "..X.....X...",
        "............",
        ".......X....",
        "....X.......",
        "..X.........",
        "............",
    ],
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "............",
        "..X.....X...",
        "............",
        ".......X....",
        "....X.......",
        "..X.........",
    ],
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "..X.........",
        "............",
        "..X.....X...",
        "............",
        ".......X....",
        "....X.......",
    ],
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "....X.......",
        "..X.........",
        "............",
        "..X.....X...",
        "............",
        ".......X....",
    ],
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        ".......X....",
        "....X.......",
        "..X.........",
        "............",
        "..X.....X...",
        "............",
    ],
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "............",
        ".......X....",
        "....X.......",
        "..X.........",
        "............",
        "..X.....X...",
    ],
]

# Snow - cloud only (flakes animated dynamically)
_SNOW = [
    [
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "............",
        "............",
        "............",
        "............",
        "............",
        "............",
    ],
]

# Thunder - two bolts strike down offset, then disappear
_THUNDER = [
    [  # frame 0: bolt1 row 1
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "...XX.......",
        "............",
        "............",
        "............",
        "............",
        "............",
    ],
    [  # frame 1: bolt1 rows 1-2
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "...XX.......",
        "..XX........",
        "............",
        "............",
        "............",
        "............",
    ],
    [  # frame 2: bolt1 rows 1-3, bolt2 row 1
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "...XX..XX...",
        "..XX........",
        ".XXXX.......",
        "............",
        "............",
        "............",
    ],
    [  # frame 3: bolt1 rows 1-4, bolt2 rows 1-2
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "...XX..XX...",
        "..XX....XX..",
        ".XXXX.......",
        "...XX.......",
        "............",
        "............",
    ],
    [  # frame 4: bolt1 rows 1-5, bolt2 rows 1-3
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "...XX..XX...",
        "..XX....XX..",
        ".XXXX.XX....",
        "...XX.......",
        "..XX........",
        "............",
    ],
    [  # frame 5: full bolt1, bolt2 rows 1-4
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        "...XX..XX...",
        "..XX....XX..",
        ".XXXX.XX....",
        "...XX..XX...",
        "..XX........",
        "...X........",
    ],
    [  # frame 6: full bolt1, full bolt2
        "....XXXX....",
        "...XXXXXX...",
        "..XXXXXXXX..",
        "XXXXXXXXXXXX",
        "XXXXXXXXXXXX",
        ".......XX...",
        "........XX..",
        "......XX....",
        ".......XX...",
        "......XX....",
        ".......X....",
    ]
]

# --- Static icons (no animation, 10 rows) ---
_STATIC_SUN = [
    [
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
    ],
]

_STATIC_MOON = [
    [
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
    ],
]

_STATIC_CLOUD = [
    [
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
    ],
]

_STATIC_RAIN = [
    [
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
    ],
]

_STATIC_SNOW = [
    [
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
    ],
]

_STATIC_THUNDER = [
    [
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
    ],
]


def _get_icon_list(code, is_day=True):
    """Return the list of icon frames for a WMO weather code."""
    if _animated_weather:
        if code is None:
            return _CLOUD
        elif code <= 1:
            return _SUN if is_day else _MOON
        elif code <= 3:
            return _CLOUD
        elif code <= 48:
            return _CLOUD  # fog
        elif code <= 57:
            return _RAIN   # drizzle
        elif code <= 67:
            return _RAIN
        elif code <= 77:
            return _SNOW
        elif code <= 82:
            return _RAIN   # showers
        elif code <= 86:
            return _SNOW   # snow showers
        else:
            return _THUNDER
    else:
        if code is None:
            return _STATIC_CLOUD
        elif code <= 1:
            return _STATIC_SUN if is_day else _STATIC_MOON
        elif code <= 3:
            return _STATIC_CLOUD
        elif code <= 48:
            return _STATIC_CLOUD
        elif code <= 57:
            return _STATIC_RAIN
        elif code <= 67:
            return _STATIC_RAIN
        elif code <= 77:
            return _STATIC_SNOW
        elif code <= 82:
            return _STATIC_RAIN
        elif code <= 86:
            return _STATIC_SNOW
        else:
            return _STATIC_THUNDER


def _get_icon(code, is_day=True, frame=0):
    """Return icon pixel art for a WMO weather code."""
    icons = _get_icon_list(code, is_day)
    return icons[frame % len(icons)]


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


def _char_width(ch):
    """Return pixel width of a single 5x7 character."""
    from font_data import FONT_5x7
    glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
    return len(glyph) if glyph else 4


def _draw_text_3x5(x, y, text, color):
    """Draw text using the compact 3x5 font."""
    from font_data import FONT_3x5
    for ch in text:
        glyph = FONT_3x5.get(ch, FONT_3x5.get(" "))
        if glyph is None:
            x += 3
            continue
        w = len(glyph)
        for col_i in range(w):
            col_byte = glyph[col_i]
            for row_i in range(5):
                if col_byte & (1 << row_i):
                    _set_pixel(x + col_i, y + row_i, color)
        x += w + 1
    return x


def _measure_text_3x5(text):
    """Measure text width in pixels using 3x5 font."""
    from font_data import FONT_3x5
    w = 0
    for ch in text:
        glyph = FONT_3x5.get(ch, FONT_3x5.get(" "))
        if glyph:
            w += len(glyph) + 1
    return w - 1 if w > 0 else 0


def _char_width_3x5(ch):
    """Return pixel width of a single 3x5 character."""
    from font_data import FONT_3x5
    glyph = FONT_3x5.get(ch, FONT_3x5.get(" "))
    return len(glyph) if glyph else 3


def _draw_icon(x, y, icon, color):
    """Draw a pixel art icon."""
    for row_i, row_str in enumerate(icon):
        for col_i, ch in enumerate(row_str):
            if ch == "X":
                _set_pixel(x + col_i, y + row_i, color)


def _draw_icon_diff(x, y, old_icon, new_icon, color):
    """Redraw only the pixels that changed between two icon frames."""
    for row_i in range(len(new_icon)):
        old_row = old_icon[row_i] if old_icon and row_i < len(old_icon) else ""
        new_row = new_icon[row_i]
        for col_i in range(len(new_row)):
            old_ch = old_row[col_i] if col_i < len(old_row) else "."
            new_ch = new_row[col_i]
            if old_ch != new_ch:
                if new_ch == "X":
                    _set_pixel(x + col_i, y + row_i, color)
                else:
                    _set_pixel(x + col_i, y + row_i, 0)


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
    global _temperature, _feels_like, _temp_high, _temp_low, _weather_code, _fetch_error
    global _lat, _lon, _location, _tz_offset, _is_day

    if _lat is None:
        _lat, _lon, _location = _geocode_zip(requests_session, ZIP_CODE)
        print(f"Weather location: {_location} ({_lat}, {_lon})")

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={_lat}&longitude={_lon}"
        f"&current=temperature_2m,apparent_temperature,weather_code,is_day"
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
        _feels_like = current.get("apparent_temperature")
        _weather_code = current.get("weather_code")
        _is_day = bool(current.get("is_day", 1))

        # Test override
        if _TEST_WEATHER_CODE is not None:
            _weather_code = _TEST_WEATHER_CODE
        if _TEST_IS_DAY is not None:
            _is_day = _TEST_IS_DAY

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
        print(f"Weather: {_temperature}F, feels={_feels_like}F, code={_weather_code}, "
              f"hi={_temp_high} lo={_temp_low}, tz=UTC{_tz_offset:+d}")
    except Exception as e:
        print(f"Weather fetch error: {e}")
        _fetch_error = True

    gc.collect()


def get_tz_offset():
    """Return auto-detected timezone offset in hours, or None if not yet known."""
    return _tz_offset


def update_config(zip_code=None, animated=None, **kwargs):
    """Update weather config and force a re-fetch."""
    global ZIP_CODE, _lat, _lon, _location, _last_fetch, _tz_offset
    global _animated_weather, _ICON_H, _needs_redraw, _drawn_icon_key
    if zip_code is not None and zip_code != ZIP_CODE:
        ZIP_CODE = zip_code
        _lat = None  # force re-geocode
        _lon = None
        _location = ""
        _tz_offset = None
        _last_fetch = 0  # force immediate re-fetch
    if animated is not None and animated != _animated_weather:
        _animated_weather = animated
        _ICON_H = 11 if _animated_weather else 10
        _drawn_icon_key = None  # force icon redraw
        _needs_redraw = True
    print(f"Weather config updated: ZIP={ZIP_CODE} animated={_animated_weather}")


def setup(bitmap, palette, pool=None, **kwargs):
    """Initialize weather mode."""
    global _bitmap, _palette, _requests, _last_fetch
    global _temperature, _feels_like, _temp_high, _temp_low, _weather_code
    global _lat, _lon, _location, _fetch_error, _needs_redraw
    global _last_minute, _prev_bottom_str, _prev_bottom_x
    global _drawn_temp_str, _drawn_temp_end_x, _drawn_icon_key
    global _drawn_hi_str, _drawn_lo_str, _drawn_feels_str, _drawn_loading
    global _icon_frame
    global _next_icon_change, _icon_showing_alt, _star_states
    global _snow_flakes, _ICON_H

    _ICON_H = 11 if _animated_weather else 10

    _bitmap = bitmap
    _palette = palette
    _last_fetch = 0
    _temperature = None
    _feels_like = None
    _temp_high = None
    _temp_low = None
    _weather_code = None
    _lat = None
    _lon = None
    _location = ""
    _fetch_error = False
    _needs_redraw = True
    _last_minute = -1
    _prev_bottom_str = None
    _prev_bottom_x = 0
    _drawn_temp_str = None
    _drawn_temp_end_x = 0
    _drawn_icon_key = None
    _drawn_hi_str = None
    _drawn_lo_str = None
    _drawn_feels_str = None
    _drawn_loading = False
    _icon_frame = 0
    _next_icon_change = 0
    _icon_showing_alt = False
    _star_states = None
    _snow_flakes = None

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
    """Build the bottom bar string (time - condition) for 3x5 font."""
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
    bottom_w = _measure_text_3x5(bottom_str)
    return bottom_str, bottom_w


def _draw_bottom_text():
    """Draw the bottom time/condition bar in 3x5 font, clearing old text first."""
    global _prev_bottom_str, _prev_bottom_x
    bottom_str, bottom_w = _build_bottom_text()
    bottom_x = (WIDTH - bottom_w) // 2

    if bottom_str == _prev_bottom_str and bottom_x == _prev_bottom_x:
        return  # nothing changed

    old_str = _prev_bottom_str or ""
    # Same length & same position: per-character diff (only redraw changed chars)
    if len(old_str) == len(bottom_str) and bottom_x == _prev_bottom_x:
        cx = bottom_x
        for i in range(len(bottom_str)):
            cw = _char_width_3x5(bottom_str[i])
            if old_str[i] != bottom_str[i]:
                _clear_rect(cx, _BOTTOM_Y, cw + 1, 5)  # +1 for gap
                _draw_text_3x5(cx, _BOTTOM_Y, bottom_str[i], 5)
            cx += cw + 1
    else:
        # Different length or position: full clear + redraw
        if old_str:
            prev_w = _measure_text_3x5(old_str)
            _clear_rect(_prev_bottom_x, _BOTTOM_Y, prev_w, 5)
        _draw_text_3x5(bottom_x, _BOTTOM_Y, bottom_str, 5)
    _prev_bottom_str = bottom_str
    _prev_bottom_x = bottom_x


def _draw_feels_like():
    """Draw 'Feels Like XX' in 3x5 font below the icon/temp area."""
    global _drawn_feels_str
    if _feels_like is not None:
        fl_int = int(round(_feels_like))
        new_str = f"Feels Like {fl_int}"
    else:
        new_str = None

    if new_str == _drawn_feels_str:
        return  # nothing changed

    old_str = _drawn_feels_str or ""

    if new_str is not None and len(old_str) == len(new_str):
        # Same length: per-character diff (only redraw changed chars)
        cx = _FEELS_X
        for i in range(len(new_str)):
            cw = _char_width_3x5(new_str[i])
            if old_str[i] != new_str[i]:
                _clear_rect(cx, _FEELS_Y, cw + 1, 5)
                _draw_text_3x5(cx, _FEELS_Y, new_str[i], 5)
            cx += cw + 1
    else:
        # Different length or None transition: full clear + redraw
        if old_str:
            old_w = _measure_text_3x5(old_str)
            _clear_rect(_FEELS_X, _FEELS_Y, old_w, 5)
        if new_str is not None:
            _draw_text_3x5(_FEELS_X, _FEELS_Y, new_str, 5)

    _drawn_feels_str = new_str


# Layout constants
_ICON_X = 12
_ICON_Y = 2
_ICON_W = 12
_ICON_H = 10  # updated dynamically: 11 if animated, 10 if static
_TEMP_X = 28
_TEMP_Y = 2
_TEMP_LARGE_H = 14  # 7 rows * 2
_HILO_X = 90
_HI_Y = 2
_LO_Y = 11
_FEELS_X = 12    # same as icon left edge
_FEELS_Y = 14    # below temp area, above bottom bar
_BOTTOM_Y = 25   # 3x5 font is 5px tall → rows 25-29


def animate(bitmap):
    """Update weather display. Returns sleep time."""
    global _last_fetch, _needs_redraw, _last_minute
    global _drawn_temp_str, _drawn_temp_end_x, _drawn_icon_key
    global _drawn_hi_str, _drawn_lo_str, _drawn_feels_str, _drawn_loading
    global _prev_bottom_str, _icon_frame
    global _next_icon_change, _icon_showing_alt, _star_states
    global _snow_flakes

    now = time.monotonic()

    # Fetch weather data periodically
    if _requests is not None and (now - _last_fetch >= REFRESH_INTERVAL or _temperature is None):
        _last_fetch = now
        _fetch_weather(_requests)
        _needs_redraw = True

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
            _needs_redraw = True

    # Nothing to update (except icon animation)
    if not _needs_redraw:
        if _animated_weather and _temperature is not None and _drawn_icon_key is not None:
            # Moon: per-star independent random twinkle
            is_moon = _weather_code is not None and _weather_code <= 1 and not _is_day
            is_snow = _weather_code is not None and _weather_code >= 71 and _weather_code <= 77 or _weather_code is not None and _weather_code >= 85 and _weather_code <= 86
            if is_moon and _star_states is not None:
                color = _drawn_icon_key[1]
                for i, (cx, cy) in enumerate(_MOON_STARS):
                    on, next_t = _star_states[i]
                    if now >= next_t:
                        on = not on
                        if on:
                            next_t = now + random.uniform(0.3, 1.0)
                        else:
                            next_t = now + random.uniform(1.5, 5.0)
                        _star_states[i] = (on, next_t)
                        _set_pixel(_ICON_X + cx, _ICON_Y + cy, color if on else 0)
            # Snow: per-flake drift (like christmas mode)
            elif is_snow and _snow_flakes is not None:
                color = _drawn_icon_key[1]
                for flake in _snow_flakes:
                    # Erase old position
                    _set_pixel(_ICON_X + flake[0], _ICON_Y + 5 + flake[1], 0)
                    # Move down 1
                    flake[1] += 1
                    # Sway sideways ~25% of the time
                    if random.randint(0, 3) == 0:
                        flake[0] += random.choice([-1, 1])
                        flake[0] = max(0, min(11, flake[0]))
                    # Wrap around
                    if flake[1] > 5:
                        flake[1] = 0
                        flake[0] = random.randint(1, 10)
                    # Draw new position
                    _set_pixel(_ICON_X + flake[0], _ICON_Y + 5 + flake[1], color)
            # Other icons: fixed-interval frame cycle
            elif not is_moon and now >= _next_icon_change:
                icons = _get_icon_list(_weather_code, _is_day)
                old_frame = _icon_frame % len(icons)
                _icon_frame += 1
                new_frame = _icon_frame % len(icons)
                is_thunder = _weather_code is not None and _weather_code >= 95
                if is_thunder:
                    _next_icon_change = now + 0.08
                else:
                    _next_icon_change = now + 0.4
                old_icon = icons[old_frame]
                new_icon = icons[new_frame]
                _draw_icon_diff(_ICON_X, _ICON_Y, old_icon, new_icon, _drawn_icon_key[1])
        return 0.5
    _needs_redraw = False

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
        _drawn_feels_str = None
        _prev_bottom_str = None

    # --- Left side: icon (12x10, animated) ---
    new_icon_key = _get_icon_key(_weather_code, _is_day)
    if _drawn_icon_key is None:
        # First draw or after loading: full draw
        _clear_rect(_ICON_X, _ICON_Y, _ICON_W, _ICON_H)
        _icon_showing_alt = False
        _next_icon_change = now + random.uniform(2.0, 6.0)
        icon = _get_icon(_weather_code, _is_day, 0)
        _draw_icon(_ICON_X, _ICON_Y, icon, new_icon_key[1])
        # Init per-star states for moon
        is_moon = _animated_weather and _weather_code is not None and _weather_code <= 1 and not _is_day
        is_snow = _animated_weather and (_weather_code is not None and _weather_code >= 71 and _weather_code <= 77 or _weather_code is not None and _weather_code >= 85 and _weather_code <= 86)
        if is_moon:
            _star_states = [(False, now + random.uniform(1.0, 4.0)) for _ in _MOON_STARS]
        else:
            _star_states = None
        if is_snow:
            # Evenly distribute flakes across rows so they don't clump
            _snow_flakes = [[random.randint(1, 10), i % 6] for i in range(7)]
        else:
            _snow_flakes = None
    else:
        cur_frame = 1 if _icon_showing_alt else 0
        icon = _get_icon(_weather_code, _is_day, cur_frame)
        _draw_icon_diff(_ICON_X, _ICON_Y, _get_icon(_weather_code, _is_day, 0), icon, new_icon_key[1])
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
            _set_pixel(new_end_x, _TEMP_Y, 3)
            _set_pixel(new_end_x + 1, _TEMP_Y, 3)
            _set_pixel(new_end_x, _TEMP_Y + 1, 3)
            _set_pixel(new_end_x + 1, _TEMP_Y + 1, 3)
            _draw_small_text(new_end_x + 3, _TEMP_Y, "F", 3)

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

    # --- Feels like (3x5 font below temp area) ---
    _draw_feels_like()

    # --- Bottom: time - conditions text (3x5 font) ---
    _draw_bottom_text()

    return 0.5
