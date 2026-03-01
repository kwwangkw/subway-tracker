# SPDX-License-Identifier: MIT
# Christmas banner — Static holiday display (no WiFi needed)
#
# Copy this as code.py to CIRCUITPY drive.
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 panels

import board
import displayio
import rgbmatrix
import framebufferio
import time
import math
import random

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

bitmap = displayio.Bitmap(WIDTH, HEIGHT, 8)
palette = displayio.Palette(8)

# Note: G↔B swapped on these panels
# To get a color, swap green and blue channels in the hex value
palette[0] = 0x000000  # black background
palette[1] = 0x080000  # red (text/trunks)
palette[2] = 0x000800  # green (trees)
palette[3] = 0x080808  # white (snow/text)
palette[4] = 0x080800  # yellow (star)
palette[5] = 0x000008  # blue (lights)
palette[6] = 0x000800  # actual green (lights)

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
# Christmas tree drawing helper
# ---------------------------------------------------------------
def draw_tree(tx, ty, c_tree, c_trunk):
    """Draw a Christmas tree. tx,ty is the top (star position)."""
    # Layer 1 (top, narrow)
    set_pixel(tx, ty, c_tree)
    draw_hline(tx - 1, ty + 1, 3, c_tree)
    draw_hline(tx - 2, ty + 2, 5, c_tree)
    draw_hline(tx - 3, ty + 3, 7, c_tree)
    # Layer 2 (wider)
    draw_hline(tx - 2, ty + 4, 5, c_tree)
    draw_hline(tx - 3, ty + 5, 7, c_tree)
    draw_hline(tx - 4, ty + 6, 9, c_tree)
    draw_hline(tx - 5, ty + 7, 11, c_tree)
    # Layer 3 (widest)
    draw_hline(tx - 3, ty + 8, 7, c_tree)
    draw_hline(tx - 4, ty + 9, 9, c_tree)
    draw_hline(tx - 5, ty + 10, 11, c_tree)
    draw_hline(tx - 6, ty + 11, 13, c_tree)
    # Trunk
    fill_rect(tx - 1, ty + 12, 3, 2, c_trunk)

def draw_small_tree(tx, ty, c_tree, c_trunk):
    """Draw a smaller Christmas tree. tx,ty is the top."""
    # Layer 1 (top)
    set_pixel(tx, ty, c_tree)
    draw_hline(tx - 1, ty + 1, 3, c_tree)
    draw_hline(tx - 2, ty + 2, 5, c_tree)
    # Layer 2
    draw_hline(tx - 1, ty + 3, 3, c_tree)
    draw_hline(tx - 2, ty + 4, 5, c_tree)
    draw_hline(tx - 3, ty + 5, 7, c_tree)
    # Layer 3
    draw_hline(tx - 2, ty + 6, 5, c_tree)
    draw_hline(tx - 3, ty + 7, 7, c_tree)
    draw_hline(tx - 4, ty + 8, 9, c_tree)
    # Trunk
    fill_rect(tx - 1, ty + 9, 3, 2, c_trunk)

# Light positions for big tree
BIG_TREE_LIGHTS = [
    (0, 1),
    (-1, 2), (1, 2),
    (-2, 3), (2, 3),
    (0, 5),
    (-3, 6), (3, 6),
    (-2, 7), (2, 7),
    (-1, 9), (1, 9),
    (-4, 10), (0, 10), (4, 10),
    (-3, 11), (3, 11),
]

# Light positions for small tree
SMALL_TREE_LIGHTS = [
    (0, 1),
    (-1, 2), (1, 2),
    (0, 4),
    (-2, 5), (2, 5),
    (-1, 7), (1, 7),
    (-3, 8), (0, 8), (3, 8),
]

LIGHT_COLORS = [1, 4, 5, 6]  # red, yellow, blue, green

def draw_tree_lights(tx, ty, frame, lights):
    """Draw blinking lights on a tree — colors shift each frame."""
    for i, (lx, ly) in enumerate(lights):
        color_idx = (i + frame) % len(LIGHT_COLORS)
        set_pixel(tx + lx, ty + ly, LIGHT_COLORS[color_idx])

# ---------------------------------------------------------------
# Draw two Christmas trees — grounded at bottom, different sizes
# ---------------------------------------------------------------
# Tree 1 — left side, big tree (14px tall + 2px trunk = bottom at ty+13)
# Grounded: ty + 13 = 31 → ty = 18
T1_X, T1_Y = 14, 18
T1_LIGHTS = BIG_TREE_LIGHTS
draw_tree(T1_X, T1_Y, 2, 1)
set_pixel(T1_X, T1_Y - 1, 4)

# Tree 2 — left side, small tree (behind/next to big one)
# Grounded: ty + 10 = 31 → ty = 21
T2_X, T2_Y = 5, 21
T2_LIGHTS = SMALL_TREE_LIGHTS
draw_small_tree(T2_X, T2_Y, 2, 1)
set_pixel(T2_X, T2_Y - 1, 4)

# Tree 3 — right side, big tree
T3_X, T3_Y = 113, 18
T3_LIGHTS = BIG_TREE_LIGHTS
draw_tree(T3_X, T3_Y, 2, 1)
set_pixel(T3_X, T3_Y - 1, 4)

# Tree 4 — right side, small tree
T4_X, T4_Y = 122, 21
T4_LIGHTS = SMALL_TREE_LIGHTS
draw_small_tree(T4_X, T4_Y, 2, 1)
set_pixel(T4_X, T4_Y - 1, 4)

# Tree 5 — left side, small tree closer to text
T5_X, T5_Y = 27, 21
T5_LIGHTS = SMALL_TREE_LIGHTS
draw_small_tree(T5_X, T5_Y, 2, 1)
set_pixel(T5_X, T5_Y - 1, 4)

# Tree 6 — right side, small tree closer to text
T6_X, T6_Y = 100, 21
T6_LIGHTS = SMALL_TREE_LIGHTS
draw_small_tree(T6_X, T6_Y, 2, 1)
set_pixel(T6_X, T6_Y - 1, 4)

# ---------------------------------------------------------------
# Snow — falling particles
# ---------------------------------------------------------------
NUM_SNOWFLAKES = 18
snowflakes = []
for _ in range(NUM_SNOWFLAKES):
    sx = random.randint(0, WIDTH - 1)
    sy = random.randint(0, HEIGHT - 1)
    speed = random.choice([1, 1, 2])  # most are slow
    snowflakes.append([sx, sy, speed])

def draw_snowflakes(c):
    for sf in snowflakes:
        set_pixel(sf[0], sf[1], c)

def update_snowflakes():
    for sf in snowflakes:
        # Erase old position
        set_pixel(sf[0], sf[1], 0)
        # Move down
        sf[1] += sf[0] % 2 + 1  # vary speed slightly by x position
        # Slight horizontal drift
        if random.randint(0, 3) == 0:
            sf[0] += random.choice([-1, 1])
            sf[0] = sf[0] % WIDTH
        # Wrap around
        if sf[1] >= HEIGHT:
            sf[1] = 0
            sf[0] = random.randint(0, WIDTH - 1)

# ---------------------------------------------------------------
# Text — 5x7 blocky font (same style as Halloween)
# ---------------------------------------------------------------
ALPHA = {
    'M': [
        "X...X",
        "XX.XX",
        "X.X.X",
        "X.X.X",
        "X...X",
        "X...X",
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
    'R': [
        "XXXX.",
        "X...X",
        "X...X",
        "XXXX.",
        "X..X.",
        "X...X",
        "X...X",
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
    'C': [
        ".XXX.",
        "X...X",
        "X....",
        "X....",
        "X....",
        "X...X",
        ".XXX.",
    ],
    'H': [
        "X...X",
        "X...X",
        "X...X",
        "XXXXX",
        "X...X",
        "X...X",
        "X...X",
    ],
    'I': [
        "XXXXX",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "XXXXX",
    ],
    'S': [
        ".XXX.",
        "X...X",
        "X....",
        ".XXX.",
        "....X",
        "X...X",
        ".XXX.",
    ],
    'T': [
        "XXXXX",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
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
    return w - spacing

# "MERRY" centered, y=6
merry_w = measure_word("MERRY", 2)
merry_x = (WIDTH - merry_w) // 2
draw_word(merry_x, 6, "MERRY", 3, 2)

# "CHRISTMAS" centered, y=16
christmas_w = measure_word("CHRISTMAS", 2)
christmas_x = (WIDTH - christmas_w) // 2
draw_word(christmas_x, 16, "CHRISTMAS", 1, 2)

# ---------------------------------------------------------------
# Done! Animate lights and snow.
# ---------------------------------------------------------------
print("Merry Christmas! Display is running.")

frame = 0
light_timer = 0

# Draw initial snow
draw_snowflakes(3)

while True:
    # Update snow every frame
    update_snowflakes()
    draw_snowflakes(3)

    # Blink tree lights every 5 frames (~0.5 sec)
    light_timer += 1
    if light_timer >= 5:
        light_timer = 0
        frame += 1

    # Redraw trees over snow damage
    draw_tree(T1_X, T1_Y, 2, 1)
    draw_small_tree(T2_X, T2_Y, 2, 1)
    draw_tree(T3_X, T3_Y, 2, 1)
    draw_small_tree(T4_X, T4_Y, 2, 1)
    draw_small_tree(T5_X, T5_Y, 2, 1)
    draw_small_tree(T6_X, T6_Y, 2, 1)

    # Draw lights on top of trees
    draw_tree_lights(T1_X, T1_Y, frame, T1_LIGHTS)
    draw_tree_lights(T2_X, T2_Y, frame + 2, T2_LIGHTS)
    draw_tree_lights(T3_X, T3_Y, frame + 3, T3_LIGHTS)
    draw_tree_lights(T4_X, T4_Y, frame + 5, T4_LIGHTS)
    draw_tree_lights(T5_X, T5_Y, frame + 1, T5_LIGHTS)
    draw_tree_lights(T6_X, T6_Y, frame + 4, T6_LIGHTS)

    # Redraw stars on top
    set_pixel(T1_X, T1_Y - 1, 4)
    set_pixel(T2_X, T2_Y - 1, 4)
    set_pixel(T3_X, T3_Y - 1, 4)
    set_pixel(T4_X, T4_Y - 1, 4)
    set_pixel(T5_X, T5_Y - 1, 4)
    set_pixel(T6_X, T6_Y - 1, 4)

    # Redraw text over snow (in case snow landed on text)
    draw_word(merry_x, 6, "MERRY", 3, 2)
    draw_word(christmas_x, 16, "CHRISTMAS", 1, 2)

    time.sleep(0.1)
