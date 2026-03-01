# SPDX-License-Identifier: MIT
# hello.py — Simple hello world display test (no WiFi needed)
#
# Rename this to code.py on your CIRCUITPY drive to run it.
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 panels

import board
import displayio
import rgbmatrix
import framebufferio
import time

from font_data import FONT_5x7, FONT_5x5, LINE_COLORS

# ---------------------------------------------------------------
# Display setup — 128x32 (two chained 64x32 panels)
# ---------------------------------------------------------------
displayio.release_displays()

matrix = rgbmatrix.RGBMatrix(
    width=128,
    height=32,
    bit_depth=4,
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
# Bitmap + palette
# ---------------------------------------------------------------
WIDTH = 128
HEIGHT = 32

bitmap = displayio.Bitmap(WIDTH, HEIGHT, 8)
palette = displayio.Palette(8)

palette[0] = 0x000000           # black
palette[1] = 0x1E1E1E           # white (12%)
palette[2] = 0x160614           # 7-train purple (12%)
palette[3] = 0x081608           # G-train green (12%)

tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
group = displayio.Group()
group.append(tile_grid)
display.root_group = group

# ---------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------
def set_pixel(x, y, color):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        bitmap[x, y] = color

def trim_glyph(glyph):
    trimmed = list(glyph)
    while trimmed and trimmed[-1] == 0x00:
        trimmed.pop()
    return trimmed

def draw_char_5x7(x, y, char, color):
    glyph = FONT_5x7.get(char, FONT_5x7.get(" "))
    if glyph is None:
        return
    trimmed = trim_glyph(glyph)
    for col, byte in enumerate(trimmed):
        for row in range(7):
            if byte & (1 << row):
                set_pixel(x + col, y + row, color)

def draw_text(x, y, text, color):
    cursor_x = x
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            continue
        trimmed = trim_glyph(glyph)
        for col, byte in enumerate(trimmed):
            for row in range(7):
                if byte & (1 << row):
                    set_pixel(cursor_x + col, y + row, color)
        cursor_x += len(trimmed) + 1

def measure_text(text):
    width = 0
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            continue
        trimmed = trim_glyph(glyph)
        width += len(trimmed) + 1
    return width

def draw_text_clipped(x, y, text, color, clip_left, clip_right):
    """Draw text clipped to a horizontal region [clip_left, clip_right)."""
    cursor_x = x
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            continue
        trimmed = trim_glyph(glyph)
        char_w = len(trimmed)
        # Skip if entirely off-screen right
        if cursor_x >= clip_right:
            break
        # Draw only if at least partially visible
        if cursor_x + char_w > clip_left:
            for col, byte in enumerate(trimmed):
                px = cursor_x + col
                if clip_left <= px < clip_right:
                    for row in range(7):
                        if byte & (1 << row):
                            set_pixel(px, y + row, color)
        cursor_x += char_w + 1

def draw_char_5x5(x, y, char, color):
    glyph = FONT_5x5.get(char.upper())
    if glyph is None:
        return
    for row in range(5):
        for col in range(5):
            if glyph[row] & (1 << (4 - col)):
                set_pixel(x + col, y + row, color)

def draw_circle(cx, cy, r, color):
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= (r * r) - 2:
                set_pixel(cx + dx, cy + dy, color)

DIR_X = 25          # direction text start x
DIR_GAP = 4         # minimum gap between direction and time text
TIME_MARGIN = 2     # right margin for time text

def draw_row(y, line_color, line_char, row_index, direction, time_text, scroll_offset=0):
    row_h = 11
    cx = 15
    radius = 5
    if y == 0:
        cy = y + row_h // 2 + 1
    else:
        cy = y + row_h // 2 - 1
    draw_circle(cx, cy, radius, line_color)
    draw_char_5x5(cx - 2, cy - 2, line_char, 0)  # black on colored circle
    text_baseline = cy - 2
    # Draw row index with tight spacing (number + period with no gap)
    num_glyph = FONT_5x7.get(row_index[0], FONT_5x7.get(" "))
    num_trimmed = trim_glyph(num_glyph)
    draw_text(3, text_baseline, row_index[0], 1)
    # Draw period right after number
    set_pixel(3 + len(num_trimmed) + 1, text_baseline + 4, 1)
    # Time text (right-aligned)
    tw = measure_text(time_text)
    time_x = WIDTH - tw - TIME_MARGIN
    draw_text(time_x, text_baseline, time_text, 1)
    # Direction text — clipped to region between DIR_X and time_x - gap
    clip_right = time_x - DIR_GAP
    dir_w = measure_text(direction)
    if dir_w <= (clip_right - DIR_X):
        # Fits — draw static
        draw_text(DIR_X, text_baseline, direction, 1)
    else:
        # Scroll — draw at offset, clipped
        draw_text_clipped(DIR_X - scroll_offset, text_baseline, direction, 1, DIR_X, clip_right)

# ---------------------------------------------------------------
# Demo data — row 1 is long (scrolls), row 2 fits (static)
# ---------------------------------------------------------------
ROW1 = (5, 2, "7", "1.", "34 ST-HUDSON YARDS", "12MIN")
ROW2 = (18, 3, "G", "2.", "CHURCH AVE", "5MIN")

# Measure if row 1 needs scrolling
row1_dir_w = measure_text(ROW1[4])
row1_tw = measure_text(ROW1[5])
row1_clip = WIDTH - row1_tw - TIME_MARGIN - DIR_GAP - DIR_X
row1_needs_scroll = row1_dir_w > row1_clip
# Total scroll distance: full text width + a gap before it repeats
SCROLL_PAD = 20  # blank pixels between end and repeat
row1_scroll_max = row1_dir_w + SCROLL_PAD if row1_needs_scroll else 0

print(f"Dir width: {row1_dir_w}, clip: {row1_clip}, scroll: {row1_needs_scroll}")
print("Display is running.")

scroll_offset = 0
SCROLL_SPEED = 1  # pixels per frame
FRAME_DELAY = 0.05  # seconds between frames

while True:
    # Clear
    for yy in range(HEIGHT):
        for xx in range(WIDTH):
            bitmap[xx, yy] = 0
    # Draw rows
    draw_row(*ROW1, scroll_offset=scroll_offset if row1_needs_scroll else 0)
    draw_row(*ROW2, scroll_offset=0)
    # Advance scroll
    if row1_needs_scroll:
        scroll_offset = (scroll_offset + SCROLL_SPEED) % row1_scroll_max
    time.sleep(FRAME_DELAY)
