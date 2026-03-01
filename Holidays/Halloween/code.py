# SPDX-License-Identifier: MIT
# Halloween banner — Static holiday display (no WiFi needed)
#
# Copy this as code.py + font_data.py to CIRCUITPY drive.
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 panels

import board
import displayio
import rgbmatrix
import framebufferio
import time
import math

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
# Bitmap + palette (12% brightness)
# ---------------------------------------------------------------
WIDTH = 128
HEIGHT = 32

bitmap = displayio.Bitmap(WIDTH, HEIGHT, 8)
palette = displayio.Palette(8)

palette[0] = 0x000000  # black background
palette[1] = 0x280C00  # orange (text & decorations)

tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
group = displayio.Group()
group.append(tile_grid)
display.root_group = group

# ---------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------
def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        bitmap[x, y] = c

def fill_rect(x, y, w, h, c):
    for dy in range(h):
        for dx in range(w):
            set_pixel(x + dx, y + dy, c)

def draw_hline(x, y, w, c):
    for dx in range(w):
        set_pixel(x + dx, y, c)

def draw_vline(x, y, h, c):
    for dy in range(h):
        set_pixel(x, y + dy, c)

# ---------------------------------------------------------------
# Cobweb — top right corner
# ---------------------------------------------------------------
# 3 radial spokes from corner (127, 0)
# Spoke: horizontal (along top edge)
draw_hline(118, 0, 10, 1)
# Spoke: vertical (along right edge)
draw_vline(127, 0, 10, 1)
# Spoke: 45° diagonal (shorter)
for i in range(8):
    set_pixel(127 - i, i, 1)

# Curved arcs connecting spokes — bowing inward toward corner
# Like the reference: concave curves between each pair of spokes

# Arc 1 (close, r~3)
# horizontal spoke → diagonal spoke (curves toward corner)
set_pixel(125, 0, 1)
set_pixel(126, 1, 1)
# diagonal spoke → vertical spoke
set_pixel(127, 2, 1)
set_pixel(126, 1, 1)

# Arc 2 (mid, r~6)
# horizontal → diagonal (sags toward corner)
set_pixel(122, 0, 1)
set_pixel(123, 1, 1)
set_pixel(124, 1, 1)
set_pixel(125, 2, 1)
# diagonal → vertical (sags toward corner)
set_pixel(126, 3, 1)
set_pixel(127, 4, 1)
set_pixel(126, 4, 1)

# Arc 3 (far, r~9)
# horizontal → diagonal (deep curve)
set_pixel(119, 0, 1)
set_pixel(120, 1, 1)
set_pixel(121, 1, 1)
set_pixel(122, 2, 1)
set_pixel(123, 3, 1)
set_pixel(124, 3, 1)
# diagonal → vertical (deep curve)
set_pixel(125, 4, 1)
set_pixel(126, 5, 1)
set_pixel(126, 6, 1)
set_pixel(127, 7, 1)
set_pixel(127, 8, 1)

# ---------------------------------------------------------------
# Spider drawing helper (reusable for animation)
# ---------------------------------------------------------------
def draw_spider(sx, sy, c):
    """Draw a spider at (sx, sy) with color index c. sy is top of head."""
    # Web thread from top to spider
    draw_vline(sx, 0, sy, c)
    # Spider head
    fill_rect(sx - 1, sy, 2, 1, c)
    # Spider body (3x3)
    fill_rect(sx - 1, sy + 1, 3, 3, c)
    # Legs — left side
    set_pixel(sx - 3, sy + 1, c)
    set_pixel(sx - 4, sy, c)
    set_pixel(sx - 3, sy + 2, c)
    set_pixel(sx - 4, sy + 3, c)
    set_pixel(sx - 3, sy + 3, c)
    set_pixel(sx - 4, sy + 2, c)
    # Legs — right side
    set_pixel(sx + 3, sy + 1, c)
    set_pixel(sx + 4, sy, c)
    set_pixel(sx + 3, sy + 2, c)
    set_pixel(sx + 4, sy + 3, c)
    set_pixel(sx + 3, sy + 3, c)
    set_pixel(sx + 4, sy + 2, c)

def clear_spider(sx, sy):
    """Erase a spider by drawing it in background color."""
    draw_spider(sx, sy, 0)

# Spider 1 config: x=10, bobs between y=9 and y=13
S1_X = 10
S1_MIN = 9
S1_MAX = 13

# Spider 2 config: x=20, bobs between y=19 and y=25
S2_X = 20
S2_MIN = 19
S2_MAX = 25

# ---------------------------------------------------------------
# Bat drawing helper (reusable for animation)
# ---------------------------------------------------------------
def draw_bat(bx, by, c):
    """Draw a bat at (bx, by) with color index c."""
    # Body
    set_pixel(bx, by, c)
    set_pixel(bx, by + 1, c)
    # Left wing
    set_pixel(bx - 1, by, c)
    set_pixel(bx - 2, by - 1, c)
    set_pixel(bx - 3, by - 1, c)
    set_pixel(bx - 4, by, c)
    set_pixel(bx - 3, by + 1, c)
    # Right wing
    set_pixel(bx + 1, by, c)
    set_pixel(bx + 2, by - 1, c)
    set_pixel(bx + 3, by - 1, c)
    set_pixel(bx + 4, by, c)
    set_pixel(bx + 3, by + 1, c)
    # Ears
    set_pixel(bx - 1, by - 1, c)
    set_pixel(bx + 1, by - 1, c)

def clear_bat(bx, by):
    draw_bat(bx, by, 0)

# Bat 1 config: x=40, bobs between y=2 and y=5
B1_X = 40
B1_MIN = 2
B1_MAX = 5

# Bat 2 config: x=90, bobs between y=3 and y=6
B2_X = 90
B2_MIN = 3
B2_MAX = 6

# ---------------------------------------------------------------
# Cat silhouette — bottom right (sitting, with tail)
# ---------------------------------------------------------------
cx, cy = 113, 24
# Body (4 wide, 6 tall)
fill_rect(cx, cy + 2, 4, 6, 1)
# Head (3x3)
fill_rect(cx, cy, 3, 3, 1)
# Ears (triangles)
set_pixel(cx, cy - 1, 1)
set_pixel(cx + 2, cy - 1, 1)
# Front legs
draw_vline(cx, cy + 8, 2, 1)
draw_vline(cx + 1, cy + 8, 2, 1)
# Back legs
draw_vline(cx + 3, cy + 8, 2, 1)

# ---------------------------------------------------------------
# Cat tail animation helper
# ---------------------------------------------------------------
# Two tail poses that alternate
TAIL_POSES = [
    # Pose 0: tail curves right (original)
    [(cx + 4, cy + 7), (cx + 5, cy + 6), (cx + 6, cy + 5), (cx + 7, cy + 4), (cx + 7, cy + 3)],
    # Pose 1: tail curves up more
    [(cx + 4, cy + 7), (cx + 5, cy + 6), (cx + 6, cy + 5), (cx + 7, cy + 5), (cx + 7, cy + 4)],
    # Pose 2: tail straighter / relaxed
    [(cx + 4, cy + 7), (cx + 5, cy + 7), (cx + 6, cy + 6), (cx + 7, cy + 5), (cx + 7, cy + 4)],
]

def draw_tail(pose_idx, c):
    for (tx, ty) in TAIL_POSES[pose_idx]:
        set_pixel(tx, ty, c)

def clear_tail(pose_idx):
    draw_tail(pose_idx, 0)

# ---------------------------------------------------------------
# "HAPPY" text — orange, centered horizontally, row ~8
# ---------------------------------------------------------------
# Using a simple 5x7-ish blocky font, but drawn manually for pixel precision
# at 12% brightness orange

ALPHA = {
    'H': [
        "X...X",
        "X...X",
        "X...X",
        "XXXXX",
        "X...X",
        "X...X",
        "X...X",
    ],
    'A': [
        ".XXX.",
        "X...X",
        "X...X",
        "XXXXX",
        "X...X",
        "X...X",
        "X...X",
    ],
    'P': [
        "XXXX.",
        "X...X",
        "X...X",
        "XXXX.",
        "X....",
        "X....",
        "X....",
    ],
    'Y': [
        "X...X",
        "X...X",
        ".X.X.",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
    ],
    'L': [
        "X....",
        "X....",
        "X....",
        "X....",
        "X....",
        "X....",
        "XXXXX",
    ],
    'O': [
        ".XXX.",
        "X...X",
        "X...X",
        "X...X",
        "X...X",
        "X...X",
        ".XXX.",
    ],
    'W': [
        "X...X",
        "X...X",
        "X...X",
        "X.X.X",
        "X.X.X",
        "XX.XX",
        "X...X",
    ],
    'E': [
        "XXXXX",
        "X....",
        "X....",
        "XXX..",
        "X....",
        "X....",
        "XXXXX",
    ],
    'N': [
        "X...X",
        "XX..X",
        "XX..X",
        "X.X.X",
        "X..XX",
        "X..XX",
        "X...X",
    ],
}

def draw_letter(x, y, ch, color):
    glyph = ALPHA.get(ch)
    if glyph is None:
        return
    for row, line in enumerate(glyph):
        for col, c in enumerate(line):
            if c == 'X':
                set_pixel(x + col, y + row, color)

def draw_word(x, y, word, color, spacing=1):
    cursor = x
    for ch in word:
        if ch == ' ':
            cursor += 2
            continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            cursor += 4
            continue
        w = len(glyph[0]) if glyph else 3
        draw_letter(cursor, y, ch, color)
        cursor += w + spacing

def measure_word(word, spacing=1):
    w = 0
    for ch in word:
        if ch == ' ':
            w += 2
            continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            w += 4
            continue
        w += len(glyph[0]) + spacing
    return w - spacing  # remove trailing spacing

# "HAPPY" centered, y=8
happy_w = measure_word("HAPPY", 2)
happy_x = (WIDTH - happy_w) // 2
draw_word(happy_x, 8, "HAPPY", 1, 2)

# "HALLOWEEN" centered, y=18
halloween_w = measure_word("HALLOWEEN", 2)
halloween_x = (WIDTH - halloween_w) // 2
draw_word(halloween_x, 18, "HALLOWEEN", 1, 2)

# ---------------------------------------------------------------
# Done! Animate spiders bobbing up and down.
# ---------------------------------------------------------------
print("Happy Halloween! Display is running.")

frame = 0
s1_prev_y = S1_MIN
s2_prev_y = S2_MIN
b1_prev_y = B1_MIN
b2_prev_y = B2_MIN
tail_prev = 0

# Draw initial positions
draw_spider(S1_X, s1_prev_y, 1)
draw_spider(S2_X, s2_prev_y, 1)
draw_bat(B1_X, b1_prev_y, 1)
draw_bat(B2_X, b2_prev_y, 1)
draw_tail(0, 1)

while True:
    # Calculate new positions using sine wave for smooth bobbing
    # Spider 1: period ~4 seconds
    s1_range = S1_MAX - S1_MIN
    s1_y = S1_MIN + int((math.sin(frame * 0.10) + 1) / 2 * s1_range)

    # Spider 2: slightly different speed, offset phase
    s2_range = S2_MAX - S2_MIN
    s2_y = S2_MIN + int((math.sin(frame * 0.08 + 2) + 1) / 2 * s2_range)

    # Bat 1: gentle bob, different phase from spiders
    b1_range = B1_MAX - B1_MIN
    b1_y = B1_MIN + int((math.sin(frame * 0.12 + 1) + 1) / 2 * b1_range)

    # Bat 2: slightly different speed/phase
    b2_range = B2_MAX - B2_MIN
    b2_y = B2_MIN + int((math.sin(frame * 0.14 + 3) + 1) / 2 * b2_range)

    # Cat tail: slow wag through 3 poses (~3 sec per cycle)
    tail_pose = int((math.sin(frame * 0.07) + 1) / 2 * 2.99)

    # Only redraw if position changed
    if s1_y != s1_prev_y:
        clear_spider(S1_X, s1_prev_y)
        draw_spider(S1_X, s1_y, 1)
        s1_prev_y = s1_y

    if s2_y != s2_prev_y:
        clear_spider(S2_X, s2_prev_y)
        draw_spider(S2_X, s2_y, 1)
        s2_prev_y = s2_y

    if b1_y != b1_prev_y:
        clear_bat(B1_X, b1_prev_y)
        draw_bat(B1_X, b1_y, 1)
        b1_prev_y = b1_y

    if b2_y != b2_prev_y:
        clear_bat(B2_X, b2_prev_y)
        draw_bat(B2_X, b2_y, 1)
        b2_prev_y = b2_y

    if tail_pose != tail_prev:
        clear_tail(tail_prev)
        draw_tail(tail_pose, 1)
        tail_prev = tail_pose

    frame += 1
    time.sleep(0.1)
