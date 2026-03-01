# SPDX-License-Identifier: MIT
# Valentine's Day banner — Floating hearts (no WiFi needed)
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
palette[1] = 0x080000  # red (hearts)
palette[2] = 0x080008  # pink — red + blue(green ch)
palette[3] = 0x080808  # white (text)
palette[4] = 0x100000  # bright red
palette[5] = 0x080010  # magenta
palette[6] = 0x100008  # hot pink (brighter red + blue)
palette[7] = 0x080800  # orange-ish (red + green ch)

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
# Heart shapes — pixel art
# ---------------------------------------------------------------
# Big heart (7x6)
BIG_HEART = [
    ".XX.XX.",
    "XXXXXXX",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "...X...",
]

# Small heart (5x4)
SMALL_HEART = [
    ".X.X.",
    "XXXXX",
    ".XXX.",
    "..X..",
]

def draw_heart(x, y, color, small=False):
    pattern = SMALL_HEART if small else BIG_HEART
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c == 'X':
                set_pixel(x + col, y + row, color)

def erase_heart(x, y, small=False):
    pattern = SMALL_HEART if small else BIG_HEART
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c == 'X':
                set_pixel(x + col, y + row, 0)

# ---------------------------------------------------------------
# Floating hearts — pre-allocated flat arrays
# ---------------------------------------------------------------
# Each heart: [x, y, speed, color, small]
# small: 0=big, 1=small
NUM_HEARTS = 8
# Store as flat: [x0,y0,spd0,col0,sm0, x1,y1,spd1,col1,sm1, ...]
hearts = [0] * (NUM_HEARTS * 5)
HEART_COLORS = [1, 1, 2, 2, 4, 5, 6, 7]

def edge_x():
    """Return a random x biased toward the left or right edges."""
    if random.randint(0, 1) == 0:
        return random.randint(0, 30)
    else:
        return random.randint(95, WIDTH - 7)

def init_hearts():
    for i in range(NUM_HEARTS):
        b = i * 5
        hearts[b] = edge_x()                            # x
        hearts[b + 1] = random.randint(0, HEIGHT - 1)   # y
        hearts[b + 2] = random.choice([1, 1, 2])        # speed
        hearts[b + 3] = random.choice(HEART_COLORS)     # color
        hearts[b + 4] = random.randint(0, 1)            # small

init_hearts()

def update_hearts():
    for i in range(NUM_HEARTS):
        b = i * 5
        sm = hearts[b + 4]
        # Erase old
        erase_heart(hearts[b], hearts[b + 1], sm)
        # Move up (hearts float upward)
        hearts[b + 1] -= hearts[b + 2]
        # Slight drift
        if random.randint(0, 4) == 0:
            hearts[b] += random.choice([-1, 1])
            if hearts[b] < 0:
                hearts[b] = 0
            if hearts[b] > WIDTH - 5:
                hearts[b] = WIDTH - 5
        # Wrap at top
        if hearts[b + 1] < -6:
            hearts[b + 1] = HEIGHT
            hearts[b] = edge_x()
            hearts[b + 3] = random.choice(HEART_COLORS)
            hearts[b + 4] = random.randint(0, 1)
        # Draw
        draw_heart(hearts[b], hearts[b + 1], hearts[b + 3], hearts[b + 4])

# (no static hearts)

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
    'V': [
        "X...X",
        "X...X",
        "X...X",
        "X...X",
        ".X.X.",
        ".X.X.",
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
        "X.X.X",
        "X.X.X",
        "X..XX",
        "X...X",
        "X...X",
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
line1 = "HAPPY"
line2 = "VALENTINE'S"
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
print("Happy Valentine's Day! Display is running.")

while True:
    update_hearts()
    draw_text()
    time.sleep(0.15)
