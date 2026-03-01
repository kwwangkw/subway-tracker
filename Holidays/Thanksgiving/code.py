# SPDX-License-Identifier: MIT
# Thanksgiving banner — Fall leaves floating down (no WiFi needed)
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

bitmap = displayio.Bitmap(WIDTH, HEIGHT, 16)
palette = displayio.Palette(16)

# Note: G↔B swapped on these panels
palette[0] = 0x000000   # black background
palette[1] = 0x100800   # bright orange
palette[2] = 0x100000   # bright red
palette[3] = 0x080800   # yellow
palette[4] = 0x080808   # white (text)
palette[5] = 0x080400   # dim orange
palette[6] = 0x080000   # dim red
palette[7] = 0x100800   # warm orange (same as 1)
palette[8] = 0x080800   # gold-yellow
palette[9] = 0x180800   # red-orange
palette[10] = 0x100000  # crimson

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
# Leaf shapes — pixel art
# ---------------------------------------------------------------
# Leaf shape 1 — maple (7x7): 3 pointed tips, tapers to curved stem
LEAF1 = [
    ".X.X.X.",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "..XY...",
    "...Y...",
    "....Y..",
]

# Leaf shape 2 — oak (6x7): lobes shift side to side, curved stem
LEAF2 = [
    "..XX..",
    ".XXXX.",
    "XXXXX.",
    ".XXXXX",
    ".XXXX.",
    "..YX..",
    "..Y...",
]

# Leaf shape 3 — pointed (5x7): narrow tip, widens toward base
LEAF3 = [
    "..X..",
    ".XX..",
    ".XXX.",
    "XXXX.",
    "XXXXX",
    ".XY..",
    "..Y..",
]

# Leaf shape 4 — small tumbling (4x5): S-curved mid-fall
LEAF4 = [
    ".X..",
    "XXX.",
    ".XXX",
    ".YX.",
    "Y...",
]

# Leaf shape 5 — round aspen (5x6): wide top, curved stem
LEAF5 = [
    ".XXX.",
    "XXXXX",
    "XXXX.",
    ".XXX.",
    "..Y..",
    ".Y...",
]

# Leaf shape 6 — tiny (3x4): small asymmetric
LEAF6 = [
    "XX.",
    "XXX",
    ".XX",
    ".Y.",
]

LEAVES = [LEAF1, LEAF2, LEAF3, LEAF4, LEAF5, LEAF6]

# Map leaf body colors to their stem/vein (darker) variant
STEM_COLOR = {
    1: 5,   # bright orange → dim orange
    2: 6,   # bright red → dim red
    3: 5,   # yellow → dim orange (brown-ish)
    5: 6,   # dim orange → dim red
    8: 5,   # gold-yellow → dim orange
    9: 6,   # red-orange → dim red
    10: 6,  # crimson → dim red
}

# Set of pixel coordinates occupied by text — built once at startup
text_pixels = set()

def draw_leaf(x, y, color, shape):
    pattern = LEAVES[shape]
    vein = STEM_COLOR.get(color, 6)
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c == 'X':
                px, py = x + col, y + row
                if (px, py) not in text_pixels:
                    set_pixel(px, py, color)
            elif c == 'Y':
                px, py = x + col, y + row
                if (px, py) not in text_pixels:
                    set_pixel(px, py, vein)

def erase_leaf(x, y, shape):
    pattern = LEAVES[shape]
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c in ('X', 'Y'):
                px, py = x + col, y + row
                if (px, py) not in text_pixels:
                    set_pixel(px, py, 0)

# ---------------------------------------------------------------
# Falling leaves — pre-allocated
# ---------------------------------------------------------------
NUM_LEAVES = 10
# Fixed-point x10: positions in tenths of pixels for smooth motion
# Flat: [x10, y10, vx10, vy10, color, shape] per leaf (6 fields)
FIELDS = 6
leaves = [0] * (NUM_LEAVES * FIELDS)
LEAF_COLORS = [1, 2, 3, 5, 8, 9, 10]  # oranges, reds, yellows
NUM_SHAPES = len(LEAVES)

def edge_x():
    """Return a random x biased toward left or right edges."""
    if random.randint(0, 1) == 0:
        return random.randint(0, 30)       # left zone
    else:
        return random.randint(95, WIDTH - 7)  # right zone

def any_x():
    """Return a random x anywhere."""
    return random.randint(0, WIDTH - 7)

def rand_speed_y():
    """Random vertical speed in tenths: 4-10 (0.4 to 1.0 px/frame)."""
    return random.randint(4, 10)

def rand_speed_x():
    """Random horizontal drift in tenths: small, with slight right bias."""
    return random.choice([-2, -1, 0, 1, 1, 2])

def init_leaves():
    for i in range(NUM_LEAVES):
        b = i * FIELDS
        if random.randint(0, 4) == 0:
            leaves[b] = any_x() * 10
        else:
            leaves[b] = edge_x() * 10
        leaves[b + 1] = random.randint(-HEIGHT, HEIGHT - 1) * 10
        leaves[b + 2] = rand_speed_x()
        leaves[b + 3] = rand_speed_y()
        leaves[b + 4] = random.choice(LEAF_COLORS)
        leaves[b + 5] = random.randint(0, NUM_SHAPES - 1)

init_leaves()

# Track last drawn integer positions to avoid unnecessary redraws
last_px = [0] * NUM_LEAVES
last_py = [0] * NUM_LEAVES

def update_leaves():
    for i in range(NUM_LEAVES):
        b = i * FIELDS
        shape = leaves[b + 5]
        old_px = last_px[i]
        old_py = last_py[i]
        # Update sub-pixel position
        leaves[b] += leaves[b + 2]      # x10 += vx10
        leaves[b + 1] += leaves[b + 3]  # y10 += vy10
        # Occasionally shift horizontal drift
        if random.randint(0, 15) == 0:
            leaves[b + 2] = rand_speed_x()
        # Clamp x
        if leaves[b] < 0:
            leaves[b] = 0
        if leaves[b] > (WIDTH - 7) * 10:
            leaves[b] = (WIDTH - 7) * 10
        # New integer pixel position
        new_px = leaves[b] // 10
        new_py = leaves[b + 1] // 10
        # Wrap at bottom
        if new_py > HEIGHT + 4:
            leaves[b + 1] = random.randint(-12, -5) * 10
            if random.randint(0, 4) == 0:
                leaves[b] = any_x() * 10
            else:
                leaves[b] = edge_x() * 10
            leaves[b + 2] = rand_speed_x()
            leaves[b + 3] = rand_speed_y()
            leaves[b + 4] = random.choice(LEAF_COLORS)
            leaves[b + 5] = random.randint(0, NUM_SHAPES - 1)
            new_px = leaves[b] // 10
            new_py = leaves[b + 1] // 10
            # Erase old position
            erase_leaf(old_px, old_py, shape)
            last_px[i] = new_px
            last_py[i] = new_py
            continue
        # Only redraw if pixel position changed
        if new_px != old_px or new_py != old_py:
            erase_leaf(old_px, old_py, shape)
            draw_leaf(new_px, new_py, leaves[b + 4], leaves[b + 5])
            last_px[i] = new_px
            last_py[i] = new_py

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
    'T': [
        "XXXXX",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
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
    'K': [
        "X...X",
        "X..X.",
        "X.X..",
        "XX...",
        "X.X..",
        "X..X.",
        "X...X",
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
    'G': [
        ".XXX.",
        "X...X",
        "X....",
        "X.XXX",
        "X...X",
        "X...X",
        ".XXX.",
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
    'V': [
        "X...X",
        "X...X",
        "X...X",
        "X...X",
        ".X.X.",
        ".X.X.",
        "..X..",
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
line2 = "THANKSGIVING"
l1_w = measure_word(line1, 2)
l1_x = (WIDTH - l1_w) // 2
l2_w = measure_word(line2, 2)
l2_x = (WIDTH - l2_w) // 2

def draw_text():
    draw_word(l1_x, 5, line1, 4, 2)   # white
    draw_word(l2_x, 16, line2, 1, 2)   # orange

def build_text_pixels():
    """Record all pixel positions used by the text so leaves never overwrite them."""
    for word, wx, wy, spacing in [(line1, l1_x, 5, 2), (line2, l2_x, 16, 2)]:
        cursor = wx
        for ch in word:
            if ch == ' ':
                cursor += 3
                continue
            glyph = ALPHA.get(ch)
            if glyph is None:
                cursor += 4
                continue
            w = len(glyph[0]) if glyph else 3
            for row, line in enumerate(glyph):
                for col, c in enumerate(line):
                    if c == 'X':
                        px, py = cursor + col, wy + row
                        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                            text_pixels.add((px, py))
            cursor += w + spacing

draw_text()
build_text_pixels()

# ---------------------------------------------------------------
# Main animation loop
# ---------------------------------------------------------------
print("Happy Thanksgiving! Display is running.")

while True:
    update_leaves()
    time.sleep(0.05)
