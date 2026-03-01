# SPDX-License-Identifier: MIT
# Beach Day banner — Sun, sand, umbrellas, and waves (no WiFi needed)
#
# Copy this as code.py to CIRCUITPY drive.
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
# Bitmap + palette
# ---------------------------------------------------------------
WIDTH = 128
HEIGHT = 32

bitmap = displayio.Bitmap(WIDTH, HEIGHT, 16)
palette = displayio.Palette(16)

# Note: G↔B swapped on these panels
# To display a color, swap G and B channels in hex
palette[0]  = 0x000000  # black background
palette[1]  = 0x000000  # unused
palette[2]  = 0x080800  # yellow (sun / text) — dimmed
palette[3]  = 0x080800  # sand (same yellow as sun — dimmed)
palette[4]  = 0x080000  # red (umbrella 1) — dimmed
palette[5]  = 0x080808  # white (wave foam / umbrella stripes) — dimmed
palette[6]  = 0x000008  # medium blue (wave dark) — dimmed
palette[7]  = 0x000808  # cyan / teal (wave crest) — dimmed
palette[8]  = 0x000008  # blue (umbrella 2) — dimmed
palette[9]  = 0x000800  # green (umbrella 3) — dimmed
palette[10] = 0x080000  # dark sand / pole — dimmed
palette[11] = 0x080800  # yellow (umbrella stripes) — dimmed
palette[12] = 0x000000  # spare
palette[13] = 0x000000  # spare
palette[14] = 0x000000  # spare
palette[15] = 0x000000  # spare

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
    'B': [
        "XXXX.",
        "X...X",
        "X...X",
        "XXXX.",
        "X...X",
        "X...X",
        "XXXX.",
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
    'C': [
        ".XXX.",
        "X...X",
        "X....",
        "X....",
        "X....",
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
    '!': [
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        ".....",
        "..X..",
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

# ---------------------------------------------------------------
# Scene layout constants
# ---------------------------------------------------------------
# Sky:   rows 0–24
# Waves: rows 25–27 (3 rows, animated)
# Sand:  rows 28–31 (4 rows)

SAND_TOP = 28
WAVE_TOP = 25
WAVE_ROWS = 3

# ---------------------------------------------------------------
# Draw static sky background
# ---------------------------------------------------------------
def draw_sky():
    pass  # black background, no fill needed

# ---------------------------------------------------------------
# Draw sun — top-right corner, circle + rays
# ---------------------------------------------------------------
SUN_CX = 112
SUN_CY = 7
SUN_R = 4

def draw_sun():
    # Filled circle
    for dy in range(-SUN_R, SUN_R + 1):
        for dx in range(-SUN_R, SUN_R + 1):
            if dx * dx + dy * dy <= SUN_R * SUN_R:
                set_pixel(SUN_CX + dx, SUN_CY + dy, 2)
    # Rays — 8 short lines
    rays = [
        (0, -1), (0, 1), (-1, 0), (1, 0),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
    ]
    for rdx, rdy in rays:
        for dist in range(SUN_R + 1, SUN_R + 3):
            set_pixel(SUN_CX + rdx * dist, SUN_CY + rdy * dist, 2)

# ---------------------------------------------------------------
# Draw sand base
# ---------------------------------------------------------------
def draw_sand():
    for y in range(SAND_TOP, HEIGHT):
        for x in range(WIDTH):
            set_pixel(x, y, 3)  # sand

# ---------------------------------------------------------------
# Beach umbrellas — drawn on top of sand
# ---------------------------------------------------------------
# Each umbrella: canopy (arc) + pole (vertical line into sand)
# Umbrella data: (pole_x, canopy_color, stripe_color)

UMBRELLAS = [
    (20, 4, 5),    # red/white
    (64, 8, 5),    # blue/white
    (106, 9, 5),   # green/white
]

# Pre-compute pole x positions so waves can skip them
POLE_XS = [u[0] for u in UMBRELLAS]

def draw_umbrella(base_x, canopy_c, stripe_c):
    """Draw umbrella with vertical pole and rounded dome canopy."""
    # Pole: straight vertical from sand up
    pole_top_y = SAND_TOP - 8
    for y in range(pole_top_y, SAND_TOP + 1):
        set_pixel(base_x, y, 10)

    # Canopy: filled semicircle (top half of circle)
    R = 6
    cy_center = pole_top_y - 1

    for dy in range(-R, 1):
        for dx in range(-R, R + 1):
            if dx * dx + dy * dy <= R * R:
                cx = base_x + dx
                cy = cy_center + dy
                # Stripe pattern: alternate every 3 columns
                if (dx // 3) % 2 == 0:
                    set_pixel(cx, cy, canopy_c)
                else:
                    set_pixel(cx, cy, stripe_c)

def draw_all_umbrellas():
    for base_x, cc, sc in UMBRELLAS:
        draw_umbrella(base_x, cc, sc)

# ---------------------------------------------------------------
# Wave animation — 3 rows of animated waves
# ---------------------------------------------------------------
# Waves scroll horizontally. We use a sine-based pattern.
# wave_offset increments each frame for motion.

wave_offset = 0

def draw_waves(offset):
    """Draw 3 rows of waves with horizontal scrolling, skipping pole positions."""
    for row in range(WAVE_ROWS):
        wy = WAVE_TOP + row
        for x in range(WIDTH):
            # Skip pole positions so poles stay visible
            if x in POLE_XS:
                continue
            # Sine wave pattern with offset for scrolling
            # Different phase per row for depth
            phase = (x + offset + row * 4) * 0.15
            val = math.sin(phase)

            if row == 0:
                # Top wave row — foam crests
                if val > 0.5:
                    set_pixel(x, wy, 5)   # white foam
                elif val > 0.0:
                    set_pixel(x, wy, 7)   # cyan crest
                else:
                    set_pixel(x, wy, 6)   # darker blue
            elif row == 1:
                # Middle wave row
                if val > 0.3:
                    set_pixel(x, wy, 7)   # cyan
                else:
                    set_pixel(x, wy, 6)   # darker blue
            else:
                # Bottom wave row — mostly dark blue, some cyan
                if val > 0.6:
                    set_pixel(x, wy, 7)   # cyan accent
                else:
                    set_pixel(x, wy, 6)   # dark blue

# ---------------------------------------------------------------
# Text positioning
# ---------------------------------------------------------------
line1 = "BEACH DAY!"

l1_w = measure_word(line1, 2)
l1_x = (WIDTH - l1_w) // 2

# Text sits in the sky area, vertically centered
TEXT_Y1 = 7

def draw_text():
    draw_word(l1_x, TEXT_Y1, line1, 2, 2)   # yellow

# ---------------------------------------------------------------
# Initial full scene draw
# ---------------------------------------------------------------
draw_sky()
draw_sun()
draw_sand()
draw_all_umbrellas()
draw_waves(0)
draw_text()

# ---------------------------------------------------------------
# Main animation loop
# ---------------------------------------------------------------
print("Beach Day! Display is running.")

frame = 0

while True:
    frame += 1

    # Update wave offset — waves scroll to the right
    wave_offset = frame

    # Redraw waves (they overwrite the 3 wave rows, but skip pole positions)
    draw_waves(wave_offset)

    time.sleep(0.12)
