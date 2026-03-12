# SPDX-License-Identifier: MIT
# Created by Kevin Wang - https://github.com/kwwangkw/
# train_sign.py - Display rendering for the subway train sign
#
# Draws the train arrival display on a displayio.Bitmap using the same
# layout as TrainSign.ipynb:
#   - Two rows, each with row index, colored line bullet, direction text, arrival time
#   - 128x32 pixel canvas (two chained 64x32 HUB75 panels)
#   - Variable-width text rendering (trailing empty columns trimmed)

import os
import displayio
from font_data import FONT_5x7, FONT_5x5, LINE_COLORS

# Brightness (0.0–1.0), read from settings.toml
BRIGHTNESS = float(os.getenv("MTA_BRIGHTNESS", "0.12"))

def _dim(r, g, b, brightness=None):
    """Scale an RGB color by brightness factor."""
    if brightness is None:
        brightness = BRIGHTNESS
    return (int(r * brightness), int(g * brightness), int(b * brightness))

# Display dimensions
WIDTH = 128
HEIGHT = 32

# Layout constants (from notebook)
ROW_H = 11
BUFFER = 2
ROW1_Y = 5
ROW2_Y = 18

# Circle bullet
CIRCLE_X = 15
CIRCLE_RADIUS = 5

# Text start after bullet
TEXT_X = 25
DIR_GAP = 4         # minimum gap between direction and time text
TIME_MARGIN = 2     # right margin for time text
SCROLL_PAD = 20     # blank pixels between scroll repeats

# Colors - we use a palette with indexed colors
# Index 0 = black (background)
# Index 1 = white (text)
# Index 2 = divider
# Index 3+ = line colors (allocated dynamically)
MAX_PALETTE_COLORS = 16
COLOR_BLACK = 0
COLOR_WHITE = 1
COLOR_DIVIDER = 2
FIRST_LINE_COLOR = 3  # line colors start here

# Pre-computed circle mask (radius 5, using r²-2 threshold like notebook)
# Stored as flat list [dx0, dy0, dx1, dy1, ...] to avoid tuple overhead
_CIRCLE_MASK = []
for _dy in range(-CIRCLE_RADIUS, CIRCLE_RADIUS + 1):
    for _dx in range(-CIRCLE_RADIUS, CIRCLE_RADIUS + 1):
        if _dx * _dx + _dy * _dy <= (CIRCLE_RADIUS * CIRCLE_RADIUS) - 2:
            _CIRCLE_MASK.append(_dx)
            _CIRCLE_MASK.append(_dy)


def _clear_bitmap(bitmap):
    """Clear the entire bitmap to black."""
    try:
        bitmap.fill(0)
    except AttributeError:
        for y in range(HEIGHT):
            for x in range(WIDTH):
                bitmap[x, y] = 0


def _set_pixel(bitmap, x, y, color_index):
    """Safely set a pixel on the bitmap."""
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        bitmap[x, y] = color_index


def _draw_circle(bitmap, cx, cy, color_index):
    """Draw a filled circle using pre-computed flat mask."""
    for i in range(0, len(_CIRCLE_MASK), 2):
        _set_pixel(bitmap, cx + _CIRCLE_MASK[i], cy + _CIRCLE_MASK[i + 1], color_index)


def _draw_char_5x5(bitmap, x, y, char, color_index):
    """
    Draw a 5x5 character from FONT_5x5 onto the bitmap.
    Row-encoded: each entry is a row, MSB = leftmost pixel.
    """
    glyph = FONT_5x5.get(char.upper())
    if glyph is None:
        return
    for row in range(5):
        for col in range(5):
            if glyph[row] & (1 << (4 - col)):
                _set_pixel(bitmap, x + col, y + row, color_index)


# Pre-compute trimmed glyphs once at import time to avoid repeated allocations
_TRIMMED = {}
for _ch, _glyph in FONT_5x7.items():
    _t = list(_glyph)
    while _t and _t[-1] == 0x00:
        _t.pop()
    _TRIMMED[_ch] = _t


def _draw_char_5x7(bitmap, x, y, char, color_index):
    """
    Draw a 5x7 character from FONT_5x7 onto the bitmap.
    Column-encoded: each entry is a column byte, bit 0 = top row.
    Trailing empty columns are trimmed.
    """
    trimmed = _TRIMMED.get(char)
    if trimmed is None:
        trimmed = _TRIMMED.get(" ")
    if trimmed is None:
        return
    for col, byte in enumerate(trimmed):
        for row in range(7):
            if byte & (1 << row):
                _set_pixel(bitmap, x + col, y + row, color_index)


def _measure_text(text):
    """Measure the pixel width of a string using variable-width 5x7 font."""
    width = 0
    for ch in text:
        trimmed = _TRIMMED.get(ch) or _TRIMMED.get(" ")
        if trimmed is None:
            continue
        width += len(trimmed) + 1  # glyph width + 1px spacing
    return width - 1 if width > 0 else 0  # remove trailing spacing


def _draw_text(bitmap, x, y, text, color_index):
    """Draw a string using variable-width 5x7 font."""
    cursor_x = x
    for ch in text:
        trimmed = _TRIMMED.get(ch) or _TRIMMED.get(" ")
        if trimmed is None:
            continue
        for col, byte in enumerate(trimmed):
            for row in range(7):
                if byte & (1 << row):
                    _set_pixel(bitmap, cursor_x + col, y + row, color_index)
        cursor_x += len(trimmed) + 1  # advance by actual width + spacing


def _draw_text_scroll(bitmap, x, y, text, color_index, clip_left, clip_right, scroll_max=0):
    """Draw scrolling text flicker-free with a TRUE single-pass approach.
    Each pixel in the clip region is written exactly once - either the glyph
    color or black. No separate clear step, so the display never shows a
    blank frame between clear and draw.
    If scroll_max > 0, a second copy is drawn for seamless looping."""

    # Pre-build a column lookup: for each px in [clip_left, clip_right),
    # store the glyph column byte (or 0 if blank/spacing).
    # We process both copies of the text (for seamless wrap).
    # col_data[px - clip_left] = column byte from font (bits = rows)
    region_w = clip_right - clip_left
    col_data = [0] * region_w

    copies = [x]
    if scroll_max > 0:
        copies.append(x + scroll_max)

    for text_x in copies:
        cursor_x = text_x
        for ch in text:
            trimmed = _TRIMMED.get(ch) or _TRIMMED.get(" ")
            if trimmed is None:
                continue
            char_w = len(trimmed)
            # Skip chars entirely past clip region
            if cursor_x >= clip_right:
                break
            # Process chars that overlap the clip region
            if cursor_x + char_w > clip_left:
                for col, byte in enumerate(trimmed):
                    px = cursor_x + col
                    if clip_left <= px < clip_right:
                        col_data[px - clip_left] = byte
            cursor_x += char_w + 1  # advance by actual width + spacing

    # Single pass: write every pixel in the clip region exactly once
    for i in range(region_w):
        px = clip_left + i
        byte = col_data[i]
        if byte:
            for row in range(7):
                if byte & (1 << row):
                    bitmap[px, y + row] = color_index
                else:
                    bitmap[px, y + row] = 0
        else:
            for row in range(7):
                bitmap[px, y + row] = 0


def _draw_divider(bitmap, y, color_index):
    """Draw a horizontal divider line."""
    for x in range(WIDTH):
        _set_pixel(bitmap, x, y, color_index)


def _draw_row_static(bitmap, y, line_color_index, line_char, row_index_text, direction, time_text):
    """
    Draw the static (non-scrolling) parts of a train arrival row:
    circle bullet, line char, row index, time text, and direction if it fits.

    Args:
        bitmap: displayio.Bitmap to draw on
        y: top y-coordinate of the row
        line_color_index: palette index for the line's color
        line_char: character to draw inside the bullet (e.g. '7', 'G')
        row_index_text: row label (e.g. '1.', '2.')
        direction: destination text (e.g. '34 ST-HUDSON')
        time_text: arrival time text (e.g. '3MIN')
    """
    # Circle vertical position - matches notebook adjustments
    if y == 0:
        circle_cy = y + ROW_H // 2 + 1  # top row: shift down 1px
    else:
        circle_cy = y + ROW_H // 2 - 1  # bottom row: shift up 1px

    # Draw colored circle bullet
    _draw_circle(bitmap, CIRCLE_X, circle_cy, line_color_index)

    # Draw line character centered inside circle (5x5, black on colored circle)
    # Shuttle routes (GS, FS, H) display as "S"
    display_char = "S" if line_char in ("GS", "FS", "H") else line_char
    _draw_char_5x5(bitmap, CIRCLE_X - 2, circle_cy - 2, display_char, COLOR_BLACK)

    # All text aligned to circle center
    text_baseline = circle_cy - 2

    # Row index label - tight spacing (number + period with no gap)
    num_trimmed = _TRIMMED.get(row_index_text[0]) or _TRIMMED.get(" ")
    _draw_text(bitmap, 3, text_baseline, row_index_text[0], COLOR_WHITE)
    # Draw period as single pixel right after number
    _set_pixel(bitmap, 3 + len(num_trimmed) + 1, text_baseline + 4, COLOR_WHITE)

    # Time text (right-aligned)
    time_width = _measure_text(time_text)
    time_x = WIDTH - time_width - TIME_MARGIN
    _draw_text(bitmap, time_x, text_baseline, time_text, COLOR_WHITE)

    # Direction text - only draw static if it fits
    clip_right = time_x - DIR_GAP
    dir_w = _measure_text(direction)
    if dir_w <= (clip_right - TEXT_X):
        _draw_text(bitmap, TEXT_X, text_baseline, direction, COLOR_WHITE)


# Worst-case time width - used for stable scroll clip boundary
_WORST_TIME_W = None

def _worst_time_w():
    global _WORST_TIME_W
    if _WORST_TIME_W is None:
        _WORST_TIME_W = _measure_text("99MIN")
    return _WORST_TIME_W


def _draw_row_scroll(bitmap, y, direction, scroll_offset, scroll_max, time_text):
    """
    Redraw ONLY the scrolling direction text region for a row.
    Uses single-pass pixel writing for flicker-free updates.

    Uses worst-case time width so the clip region stays constant
    regardless of current minutes (prevents frozen trailing pixels
    when time text changes width).
    """
    if y == 0:
        circle_cy = y + ROW_H // 2 + 1
    else:
        circle_cy = y + ROW_H // 2 - 1
    text_baseline = circle_cy - 2

    # Use worst-case time width for a stable clip boundary
    clip_right = WIDTH - _worst_time_w() - TIME_MARGIN - DIR_GAP

    _draw_text_scroll(bitmap, TEXT_X - scroll_offset, text_baseline, direction, COLOR_WHITE, TEXT_X, clip_right, scroll_max)


def create_display_group(brightness=None):
    """
    Create and return a displayio.Group containing the train sign.

    Args:
        brightness: float 0.0–1.0 to scale all colors. Defaults to BRIGHTNESS.

    Returns:
        (group, bitmap, palette) - the group to show on display,
        and the bitmap/palette for updating.
    """
    if brightness is None:
        brightness = BRIGHTNESS

    bitmap = displayio.Bitmap(WIDTH, HEIGHT, MAX_PALETTE_COLORS)
    palette = displayio.Palette(MAX_PALETTE_COLORS)

    # Base colors (dimmed)
    palette[COLOR_BLACK] = 0x000000
    wr, wg, wb = _dim(0xFF, 0xFF, 0xFF, brightness)
    palette[COLOR_WHITE] = (wr << 16) | (wg << 8) | wb
    dr, dg, db = _dim(0x28, 0x28, 0x28, brightness)
    palette[COLOR_DIVIDER] = (dr << 16) | (dg << 8) | db

    tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
    group = displayio.Group()
    group.append(tile_grid)

    return group, bitmap, palette


def _get_line_color_index(palette, route_id, color_map):
    """
    Get or allocate a palette index for a line color.
    color_map tracks {route_id: palette_index}.
    """
    if route_id in color_map:
        return color_map[route_id]

    color = LINE_COLORS.get(route_id, (0x80, 0x80, 0x80))
    idx = FIRST_LINE_COLOR + len(color_map)
    if idx >= MAX_PALETTE_COLORS:
        idx = FIRST_LINE_COLOR  # wrap around if too many

    r, g, b = _dim(*color)
    palette[idx] = (r << 16) | (g << 8) | b
    color_map[route_id] = idx
    return idx


def _format_time(minutes):
    """Format minutes into display text."""
    if minutes <= 0:
        return "NOW"
    elif minutes == 1:
        return "1MIN"
    else:
        return f"{minutes}MIN"


def update_display_static(bitmap, palette, arrivals):
    """
    Draw all static elements (circles, row numbers, time, non-scrolling directions).
    Call this once when data changes, NOT every scroll frame.

    Args:
        bitmap: displayio.Bitmap (128x32)
        palette: displayio.Palette
        arrivals: list of dicts from mta_feed.fetch_arrivals()
    """
    _clear_bitmap(bitmap)

    # Track palette allocations for line colors
    color_map = {}

    row_positions = [ROW1_Y, ROW2_Y]

    for i, row_y in enumerate(row_positions):
        if i >= len(arrivals):
            break

        arrival = arrivals[i]
        route_id = arrival["route_id"]
        destination = arrival["destination"].upper()
        time_text = _format_time(arrival["minutes"])
        row_index_text = f"{i + 1}."

        line_color_idx = _get_line_color_index(palette, route_id, color_map)
        _draw_row_static(bitmap, row_y, line_color_idx, route_id, row_index_text, destination, time_text)


def update_display_scroll(bitmap, arrivals, scroll_offsets, scroll_maxes):
    """
    Update ONLY the scrolling direction text regions. Flicker-free single-pass.
    Call this every scroll frame.

    Args:
        bitmap: displayio.Bitmap (128x32)
        arrivals: list of dicts
        scroll_offsets: list of int scroll offsets per row
        scroll_maxes: list of int scroll max distances per row
    """
    row_positions = [ROW1_Y, ROW2_Y]

    for i, row_y in enumerate(row_positions):
        if i >= len(arrivals):
            break
        if scroll_maxes[i] > 0:
            destination = arrivals[i]["destination"].upper()
            time_text = _format_time(arrivals[i]["minutes"])
            _draw_row_scroll(bitmap, row_y, destination, scroll_offsets[i], scroll_maxes[i], time_text)


def update_time_only(bitmap, arrivals):
    """
    Redraw ONLY the time text for each row (right-aligned).
    Clears just the time region, no full screen clear - prevents flicker.
    """
    row_positions = [ROW1_Y, ROW2_Y]

    for i, row_y in enumerate(row_positions):
        if i >= len(arrivals):
            break

        if row_y == 0:
            circle_cy = row_y + ROW_H // 2 + 1
        else:
            circle_cy = row_y + ROW_H // 2 - 1
        text_baseline = circle_cy - 2

        time_text = _format_time(arrivals[i]["minutes"])
        time_width = _measure_text(time_text)
        time_x = WIDTH - time_width - TIME_MARGIN

        # Clear from the worst-case direction clip edge to the right edge.
        # This erases both the old time text AND any frozen destination
        # pixels in the gap when time width changes (e.g. 9MIN -> 10MIN).
        clear_left = WIDTH - _worst_time_w() - TIME_MARGIN - DIR_GAP
        for px in range(clear_left, WIDTH):
            for row in range(7):
                py = text_baseline + row
                if 0 <= py < HEIGHT:
                    bitmap[px, py] = 0

        # Draw new time text
        _draw_text(bitmap, time_x, text_baseline, time_text, COLOR_WHITE)


def update_display(bitmap, palette, arrivals, scroll_offsets=None):
    """
    Legacy full redraw - clears and redraws everything.
    Used for initial draw and data refreshes.

    Args:
        bitmap: displayio.Bitmap (128x32)
        palette: displayio.Palette
        arrivals: list of dicts from mta_feed.fetch_arrivals()
            Each dict has: route_id, direction, destination, minutes
        scroll_offsets: list of int scroll offsets per row (or None for static)
    """
    _clear_bitmap(bitmap)

    # Track palette allocations for line colors
    color_map = {}

    row_positions = [ROW1_Y, ROW2_Y]

    for i, row_y in enumerate(row_positions):
        if i >= len(arrivals):
            break

        arrival = arrivals[i]
        route_id = arrival["route_id"]
        destination = arrival["destination"].upper()
        time_text = _format_time(arrival["minutes"])
        row_index_text = f"{i + 1}."

        line_color_idx = _get_line_color_index(palette, route_id, color_map)

        # Draw static parts
        _draw_row_static(bitmap, row_y, line_color_idx, route_id, row_index_text, destination, time_text)


def needs_scroll(direction):
    """Check if a direction string needs scrolling and return scroll max.
    Returns 0 if no scrolling needed, otherwise the scroll wrap distance."""
    # Use worst-case time width (double digit: "99MIN" = 25px)
    time_w = _measure_text("99MIN")
    clip_w = WIDTH - time_w - TIME_MARGIN - DIR_GAP - TEXT_X
    dir_w = _measure_text(direction.upper())
    if dir_w <= clip_w:
        return 0
    return dir_w + SCROLL_PAD


_MODE_TITLES = {
    "train": "NYC SUBWAY",
    "clock": "CLOCK",
    "weather": "WEATHER",
    "stocks": "STOCKS",
    "christmas": "CHRISTMAS",
    "halloween": "HALLOWEEN",
    "july4th": "4TH OF JULY",
    "newyear": "NEW YEAR",
    "stpatricks": "ST PATRICKS",
    "thanksgiving": "THANKSGIVING",
    "valentines": "VALENTINES",
    "beachday": "BEACH DAY",
    "birthday": "BIRTHDAY",
}


def draw_loading_screen(bitmap, palette, mode=None):
    """Draw a centered loading message on startup."""
    _clear_bitmap(bitmap)

    line_h = 7
    gap = 3
    total_h = line_h * 2 + gap
    top_y = (HEIGHT - total_h) // 2

    l1 = _MODE_TITLES.get(mode, "NYC SUBWAY") if mode else "NYC SUBWAY"
    l2 = "LOADING"
    l1_x = (WIDTH - _measure_text(l1)) // 2
    l2_x = (WIDTH - _measure_text(l2)) // 2

    _draw_text(bitmap, l1_x, top_y, l1, COLOR_WHITE)
    _draw_text(bitmap, l2_x, top_y + line_h + gap, l2, COLOR_WHITE)

    # Return info needed for dot animation
    dots_x = l2_x + _measure_text(l2) + 1  # +1 for spacing after last char
    dots_y = top_y + line_h + gap
    return dots_x, dots_y


def draw_loading_dots(bitmap, dots_x, dots_y, dot_count):
    """Draw 0-3 dots after 'LOADING' text. Call repeatedly to animate."""
    dot_w = _measure_text(".") + 1  # char advance = glyph width + spacing
    for i in range(3):
        x = dots_x + i * dot_w
        # Clear or draw each dot position
        if i < dot_count:
            _draw_text(bitmap, x, dots_y, ".", COLOR_WHITE)
        else:
            # Erase dot area
            for dx in range(dot_w):
                for dy in range(7):
                    _set_pixel(bitmap, x + dx, dots_y + dy, COLOR_BLACK)


def draw_error_screen(bitmap, palette, msg="ERROR"):
    """Draw an error message."""
    _clear_bitmap(bitmap)

    _draw_text(bitmap, 4, 4, "ERROR", COLOR_WHITE)
    # Truncate message
    if len(msg) > 20:
        msg = msg[:20]
    _draw_text(bitmap, 4, 16, msg.upper(), COLOR_WHITE)


def draw_no_wifi_screen(bitmap, palette):
    """Draw a 'No WiFi' message centered on screen."""
    _clear_bitmap(bitmap)

    line_h = 7
    gap = 3
    total_h = line_h * 2 + gap
    top_y = (HEIGHT - total_h) // 2

    l1 = "NO WIFI"
    l2 = "CHECK CONNECTION"
    l1_x = (WIDTH - _measure_text(l1)) // 2
    l2_x = (WIDTH - _measure_text(l2)) // 2

    _draw_text(bitmap, l1_x, top_y, l1, COLOR_WHITE)
    _draw_text(bitmap, l2_x, top_y + line_h + gap, l2, COLOR_WHITE)
