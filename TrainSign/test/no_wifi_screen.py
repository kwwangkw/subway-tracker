# SPDX-License-Identifier: MIT
# no_wifi_screen.py — Standalone preview of the "No WiFi" screen
#
# Rename this to code.py on your CIRCUITPY drive to run it.
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 panels

import board
import displayio
import rgbmatrix
import framebufferio
import time

from font_data import FONT_5x7

# ---------------------------------------------------------------
# Display setup — 128x32 (two chained 64x32 panels)
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
# Bitmap + palette
# ---------------------------------------------------------------
WIDTH = 128
HEIGHT = 32

bitmap = displayio.Bitmap(WIDTH, HEIGHT, 4)
palette = displayio.Palette(4)

palette[0] = 0x000000  # black
palette[1] = 0x080808  # white (dimmed)

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
    return width - 1  # remove trailing space

# ---------------------------------------------------------------
# Draw the "No WiFi" screen — centered
# ---------------------------------------------------------------
LINE_H = 7
GAP = 3  # pixels between lines
total_h = LINE_H * 2 + GAP
top_y = (HEIGHT - total_h) // 2

line1 = "NO WIFI"
line2 = "CHECK CONNECTION"
l1_x = (WIDTH - measure_text(line1)) // 2
l2_x = (WIDTH - measure_text(line2)) // 2

draw_text(l1_x, top_y, line1, 1)
draw_text(l2_x, top_y + LINE_H + GAP, line2, 1)

print("No WiFi screen is displayed.")

while True:
    time.sleep(1)
