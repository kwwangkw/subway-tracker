# modes/clock.py — Digital Clock mode
#
# Displays a large digital clock with date.
# Uses NTP-synced time from mta_feed.EPOCH_OFFSET.
# Timezone auto-detected from weather zip code.

import time
import os
import math

from train_sign import _dim, COLOR_BLACK, COLOR_WHITE
from mta_feed import EPOCH_OFFSET

WIDTH = 128
HEIGHT = 32

# Timezone offset in hours from UTC — auto-set from weather API
TZ_OFFSET = int(os.getenv("CLOCK_TZ_OFFSET", "-5"))

_bitmap = None
_palette = None
_last_minute = -1
_colon_on = True
_prev_digits = None   # (h1, h2, m1, m2, ampm) from last draw
_prev_date = None      # date string from last draw
_digit_positions = []  # list of (x, y, width, height) for each digit slot

# Large 8x12 digit font for clock display (row-encoded, 8 bits wide, MSB=left)
DIGITS_8x12 = {
    "0": [0x3C,0x7E,0xE7,0xC3,0xC3,0xC3,0xC3,0xC3,0xC3,0xE7,0x7E,0x3C],
    "1": [0x18,0x38,0x78,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x7E,0x7E],
    "2": [0x3C,0x7E,0xC7,0x03,0x03,0x06,0x0C,0x18,0x30,0x60,0xFF,0xFF],
    "3": [0x3C,0x7E,0xC7,0x03,0x03,0x1E,0x1E,0x03,0x03,0xC7,0x7E,0x3C],
    "4": [0xC3,0xC3,0xC3,0xC3,0xC3,0xFF,0xFF,0x03,0x03,0x03,0x03,0x03],
    "5": [0xFF,0xFF,0xC0,0xC0,0xC0,0xFE,0x7E,0x03,0x03,0xC7,0x7E,0x3C],
    "6": [0x3C,0x7E,0xC7,0xC0,0xC0,0xFE,0xFF,0xC3,0xC3,0xE7,0x7E,0x3C],
    "7": [0xFF,0xFF,0x03,0x03,0x06,0x0C,0x18,0x18,0x18,0x18,0x18,0x18],
    "8": [0x3C,0x7E,0xE7,0xC3,0xC3,0x7E,0x7E,0xC3,0xC3,0xE7,0x7E,0x3C],
    "9": [0x3C,0x7E,0xE7,0xC3,0xC3,0xFF,0x7F,0x03,0x03,0xC7,0x7E,0x3C],
}

# Days and months for date display
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c


def _draw_large_digit(x, y, digit, color):
    """Draw an 8x12 digit at (x, y)."""
    rows = DIGITS_8x12.get(digit)
    if rows is None:
        return
    for row_i, row_byte in enumerate(rows):
        for col_i in range(8):
            if row_byte & (0x80 >> col_i):
                _set_pixel(x + col_i, y + row_i, color)


def _draw_colon(x, y, color):
    """Draw colon (2x2 dots), always on."""
    for dx in (0, 1):
        for dy in (3, 4):
            _set_pixel(x + dx, y + dy, color)
        for dy in (8, 9):
            _set_pixel(x + dx, y + dy, color)


def _draw_small_text(x, y, text, color):
    """Draw text using the 5x7 font from train_sign."""
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
        # Advance — most glyphs are 4 cols + 1 spacer, M/W/V are 5
        x += w + 1
    return x


def _unix_to_local(unix_ts):
    """Convert Unix timestamp to local time components using TZ_OFFSET.
    Returns (year, month, day, hour, minute, second, weekday).
    """
    # Apply timezone offset
    ts = unix_ts + TZ_OFFSET * 3600

    # Days since epoch (Jan 1, 1970)
    days = ts // 86400
    remaining = ts % 86400
    if remaining < 0:
        days -= 1
        remaining += 86400

    hour = remaining // 3600
    minute = (remaining % 3600) // 60
    second = remaining % 60

    # Weekday: Jan 1 1970 was Thursday (3)
    weekday = (days + 3) % 7  # 0=Mon, 6=Sun

    # Date calculation from days since epoch
    y = 1970
    while True:
        leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
        days_in_year = 366 if leap else 365
        if days < days_in_year:
            break
        days -= days_in_year
        y += 1

    leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30,
                  31, 31, 30, 31, 30, 31]
    m = 0
    while m < 12 and days >= month_days[m]:
        days -= month_days[m]
        m += 1

    return y, m + 1, days + 1, hour, minute, second, weekday


def update_timezone(tz):
    """Update timezone offset and force redraw."""
    global TZ_OFFSET, _last_minute, _prev_digits, _prev_date
    TZ_OFFSET = tz
    _last_minute = -1
    _prev_digits = None
    _prev_date = None
    print(f"Clock timezone updated: UTC{tz:+d}")


def setup(bitmap, palette, **kwargs):
    """Initialize clock mode."""
    global _bitmap, _palette, _last_minute, _prev_digits, _prev_date

    _bitmap = bitmap
    _palette = palette
    _last_minute = -1
    _prev_digits = None
    _prev_date = None

    # Set up colors
    palette[COLOR_BLACK] = 0x000000
    wr, wg, wb = _dim(0xFF, 0xFF, 0xFF)
    palette[COLOR_WHITE] = (wr << 16) | (wg << 8) | wb

    # Cyan for time digits
    cr, cg, cb = _dim(0x00, 0xCC, 0xFF)
    palette[3] = (cr << 16) | (cg << 8) | cb

    # Dim white for date
    dr, dg, db = _dim(0x88, 0x88, 0x88)
    palette[4] = (dr << 16) | (dg << 8) | db

    # Clear display
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    print(f"Clock mode: UTC{TZ_OFFSET:+d}")


def _clear_rect(x, y, w, h):
    """Clear a rectangular region to black."""
    for py in range(y, y + h):
        for px in range(x, x + w):
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                _bitmap[px, py] = 0


def animate(bitmap):
    """Update clock display. Returns sleep time."""
    global _last_minute, _prev_digits, _prev_date

    now_unix = time.time() + EPOCH_OFFSET
    year, month, day, hour, minute, second, weekday = _unix_to_local(now_unix)

    # Only redraw when the minute changes
    if minute == _last_minute:
        return 0.5
    _last_minute = minute

    # --- Compute current digits ---
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    is_pm = hour >= 12

    h1 = str(display_hour // 10) if display_hour >= 10 else ""
    h2 = str(display_hour % 10)
    m1 = str(minute // 10)
    m2 = str(minute % 10)
    ampm = "PM" if is_pm else "AM"
    cur_digits = (h1, h2, m1, m2, ampm)

    # --- Layout constants ---
    digit_w = 8
    digit_h = 12
    gap = 2
    colon_w = 4
    ampm_gap = 3
    ampm_w = 14
    time_y = 3
    time_color = 3

    if h1:
        time_w = digit_w + gap + digit_w + gap + colon_w + gap + digit_w + gap + digit_w
    else:
        time_w = digit_w + gap + colon_w + gap + digit_w + gap + digit_w

    total_w = time_w + ampm_gap + ampm_w
    base_x = (WIDTH - total_w) // 2

    # --- Compute x positions for each slot ---
    x = base_x
    positions = []  # (x, digit_char) for h1, h2, m1, m2

    if h1:
        positions.append(x)  # h1 position
        x += digit_w + gap
    else:
        positions.append(None)  # no h1

    positions.append(x)  # h2 position
    x += digit_w + gap

    colon_x = x
    x += colon_w + gap

    positions.append(x)  # m1 position
    x += digit_w + gap
    positions.append(x)  # m2 position
    x += digit_w

    ampm_x = x + ampm_gap

    # --- First draw: full render ---
    if _prev_digits is None:
        # Clear entire display
        for y in range(HEIGHT):
            for px in range(WIDTH):
                bitmap[px, y] = 0

        # Draw all digits
        if h1 and positions[0] is not None:
            _draw_large_digit(positions[0], time_y, h1, time_color)
        _draw_large_digit(positions[1], time_y, h2, time_color)
        _draw_colon(colon_x, time_y, time_color)
        _draw_large_digit(positions[2], time_y, m1, time_color)
        _draw_large_digit(positions[3], time_y, m2, time_color)
        _draw_small_text(ampm_x, time_y + 3, ampm, 4)

        # Draw date
        day_name = DAYS[weekday]
        month_name = MONTHS[month - 1]
        date_str = f"{day_name} {month_name} {day}"
        from font_data import FONT_5x7
        text_w = 0
        for ch in date_str:
            glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
            if glyph:
                text_w += len(glyph) + 1
        text_w -= 1
        date_x = (WIDTH - text_w) // 2
        date_y = 22
        _draw_small_text(date_x, date_y, date_str, 4)

        _prev_digits = cur_digits
        _prev_date = date_str
        return 0.5

    # --- Incremental update: only redraw changed parts ---
    prev_h1, prev_h2, prev_m1, prev_m2, prev_ampm = _prev_digits

    # Check if h1 presence changed (e.g. 12:59 -> 1:00)
    h1_changed = (h1 != prev_h1)
    if h1_changed and (bool(h1) != bool(prev_h1)):
        # Layout shift — full redraw needed
        _prev_digits = None
        _prev_date = None
        _last_minute = -1  # force re-entry
        return 0.05

    # Update only changed digits
    if h1 != prev_h1 and positions[0] is not None:
        _clear_rect(positions[0], time_y, digit_w, digit_h)
        if h1:
            _draw_large_digit(positions[0], time_y, h1, time_color)

    if h2 != prev_h2:
        _clear_rect(positions[1], time_y, digit_w, digit_h)
        _draw_large_digit(positions[1], time_y, h2, time_color)

    if m1 != prev_m1:
        _clear_rect(positions[2], time_y, digit_w, digit_h)
        _draw_large_digit(positions[2], time_y, m1, time_color)

    if m2 != prev_m2:
        _clear_rect(positions[3], time_y, digit_w, digit_h)
        _draw_large_digit(positions[3], time_y, m2, time_color)

    if ampm != prev_ampm:
        _clear_rect(ampm_x, time_y + 3, ampm_w, 7)
        _draw_small_text(ampm_x, time_y + 3, ampm, 4)

    # Update date if day changed
    day_name = DAYS[weekday]
    month_name = MONTHS[month - 1]
    date_str = f"{day_name} {month_name} {day}"
    if date_str != _prev_date:
        # Clear date row and redraw
        _clear_rect(0, 22, WIDTH, 8)
        from font_data import FONT_5x7
        text_w = 0
        for ch in date_str:
            glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
            if glyph:
                text_w += len(glyph) + 1
        text_w -= 1
        date_x = (WIDTH - text_w) // 2
        _draw_small_text(date_x, 22, date_str, 4)
        _prev_date = date_str

    _prev_digits = cur_digits
    return 0.5
