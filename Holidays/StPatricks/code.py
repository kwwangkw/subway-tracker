# SPDX-License-Identifier: MIT
# St. Patrick's Day banner — Shamrocks and green (no WiFi needed)
#
# Copy this as code.py to CIRCUITPY drive.
# Hardware: Adafruit MatrixPortal S3 + two chained 64x32 HUB75 panels

import board
import displayio
import rgbmatrix
import framebufferio
import time
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
palette[0] = 0x000000  # black background
palette[1] = 0x000800  # green (shamrocks/text) — via blue channel
palette[2] = 0x000400  # dark green (stems)
palette[3] = 0x080808  # white (text)
palette[4] = 0x000C00  # bright green
palette[5] = 0x080800  # yellow/gold
palette[6] = 0x040400  # dim yellow
palette[7] = 0x000800  # green

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

# ---------------------------------------------------------------
# Shamrock shape — pixel art (9x9 with stem)
# ---------------------------------------------------------------
SHAMROCK = [
    ".XX...XX.",
    "XXXX.XXXX",
    "XXXX.XXXX",
    ".XXXXXXX.",
    "...XXX...",
    ".XXXXXXX.",
    "XXXX.XXXX",
    "XXXX.XXXX",
    ".XX...XX.",
    "....X....",
    "...X.....",
]

SMALL_SHAMROCK = [
    "XX.XX",
    "XXXXX",
    ".XXX.",
    "XXXXX",
    "XX.XX",
    "..X..",
    ".X...",
]

def draw_shamrock(x, y, color, stem_color, small=False):
    pattern = SMALL_SHAMROCK if small else SHAMROCK
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c == 'X':
                # Last 1-2 rows are stem
                if small and row >= 5:
                    set_pixel(x + col, y + row, stem_color)
                elif not small and row >= 9:
                    set_pixel(x + col, y + row, stem_color)
                else:
                    set_pixel(x + col, y + row, color)

# ---------------------------------------------------------------
# Floating shamrocks — pre-allocated
# ---------------------------------------------------------------
NUM_SHAMS = 3
# Flat: [x, y, speed, color, small] per shamrock
shams = [0] * (NUM_SHAMS * 5)
SHAM_COLORS = [1]
STEM_COLOR = 2

def edge_x():
    """Return a random x biased toward the left or right edges."""
    if random.randint(0, 1) == 0:
        return random.randint(0, 30)        # left edge zone
    else:
        return random.randint(95, WIDTH - 9) # right edge zone

def init_shamrocks():
    for i in range(NUM_SHAMS):
        b = i * 5
        shams[b] = edge_x()
        shams[b + 1] = random.randint(0, HEIGHT + 5)
        shams[b + 2] = random.choice([1, 1, 2])
        shams[b + 3] = random.choice(SHAM_COLORS)
        shams[b + 4] = random.randint(0, 1)

init_shamrocks()

def update_shamrock_positions():
    for i in range(NUM_SHAMS):
        b = i * 5
        # Save old position
        old_x = shams[b]
        old_y = shams[b + 1]
        sm = shams[b + 4]

        # Move
        shams[b + 1] -= shams[b + 2]
        if random.randint(0, 4) == 0:
            shams[b] += random.choice([-1, 1])
            if shams[b] < 0:
                shams[b] = 0
            if shams[b] > WIDTH - 5:
                shams[b] = WIDTH - 5

        # Wrap
        if shams[b + 1] < -11:
            shams[b + 1] = HEIGHT + 2
            shams[b] = edge_x()
            shams[b + 3] = random.choice(SHAM_COLORS)
            shams[b + 4] = random.randint(0, 1)
            sm = shams[b + 4]

        new_x = shams[b]
        new_y = shams[b + 1]
        pattern = SMALL_SHAMROCK if sm else SHAMROCK

        # Erase old, then immediately draw new (tight together to minimize flicker)
        for row, line in enumerate(pattern):
            for col, c in enumerate(line):
                if c == 'X':
                    px = old_x + col
                    py = old_y + row
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        bitmap[px, py] = 0
        # Draw new position right away
        draw_shamrock(new_x, new_y, shams[b + 3], 2, sm)

def draw_all_floaters():
    for i in range(NUM_SHAMS):
        b = i * 5
        draw_shamrock(shams[b], shams[b + 1], shams[b + 3], 2, shams[b + 4])

# (no static shamrocks)

# ---------------------------------------------------------------
# Text — 5x7 blocky font
# ---------------------------------------------------------------
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
    'R': [
        "XXXX.",
        "X...X",
        "X...X",
        "XXXX.",
        "X..X.",
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
    'C': [
        ".XXX.",
        "X...X",
        "X....",
        "X....",
        "X....",
        "X...X",
        ".XXX.",
    ],
    'K': [
        "X...X",
        "X..X.",
        "X.X..",
        "XX...",
        "X.X..",
        "X..X.",
        "X...X",
    ],
    'D': [
        "XXXX.",
        "X...X",
        "X...X",
        "X...X",
        "X...X",
        "X...X",
        "XXXX.",
    ],
    '\'': [
        "..X..",
        "..X..",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
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
            cursor += 3
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
            w += 3
            continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            w += 4
            continue
        w += len(glyph[0]) + spacing
    return w - spacing

# Text positioning
line1 = "HAPPY ST"
line2 = "PATRICK'S DAY"
l1_w = measure_word(line1, 2)
l1_x = (WIDTH - l1_w) // 2
l2_w = measure_word(line2, 2)
l2_x = (WIDTH - l2_w) // 2

def draw_text():
    draw_word(l1_x, 5, line1, 3, 2)
    draw_word(l2_x, 16, line2, 1, 2)

draw_text()

# ---------------------------------------------------------------
# Main animation loop
# ---------------------------------------------------------------
print("Happy St. Patrick's Day! Display is running.")

while True:
    update_shamrock_positions()
    draw_text()
    time.sleep(0.15)
