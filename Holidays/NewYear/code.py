# SPDX-License-Identifier: MIT
# New Year banner — Animated fireworks display (no WiFi needed)
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
palette[1] = 0x180000  # red
palette[2] = 0x100800  # gold/orange
palette[3] = 0x080808  # white (text)
palette[4] = 0x000018  # blue
palette[5] = 0x001800  # green
palette[6] = 0x180010  # magenta/pink
palette[7] = 0x001818  # cyan

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
    'N': [
        "X...X",
        "XX..X",
        "X.X.X",
        "X.X.X",
        "X..XX",
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
    'W': [
        "X...X",
        "X...X",
        "X...X",
        "X.X.X",
        "X.X.X",
        "XX.XX",
        "X...X",
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
    '!': [
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        "..X..",
        ".....",
        "..X..",
    ],
    '2': [
        ".XXX.",
        "X...X",
        "....X",
        "..XX.",
        ".X...",
        "X....",
        "XXXXX",
    ],
    '0': [
        ".XXX.",
        "X...X",
        "X..XX",
        "X.X.X",
        "XX..X",
        "X...X",
        ".XXX.",
    ],
    '6': [
        ".XXX.",
        "X....",
        "X....",
        "XXXX.",
        "X...X",
        "X...X",
        ".XXX.",
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
# Firework system — memory-efficient for CircuitPython
# ---------------------------------------------------------------
# Each firework is stored as a flat list to minimize memory:
# [x, y, target_y, color, phase, age, p0x, p0y, p1x, p1y, ... ]
# phase: 0=launch, 1=explode, 2=fade, 3=done
#
# We pre-allocate a fixed number of firework slots.

FIREWORK_COLORS = [1, 3, 4, 5, 6, 7]

# Color triples — each firework gets 3 colors for its particles
# Maps base color index → (secondary, tertiary)
COLOR_TRIPLE = {
    1: (6, 3),   # red → magenta, white
    3: (7, 1),   # white → cyan, red
    4: (7, 6),   # blue → cyan, magenta
    5: (7, 3),   # green → cyan, white
    6: (1, 4),   # magenta → red, blue
    7: (4, 5),   # cyan → blue, green
}

def particle_color(base, i):
    """Cycle particle colors: base, secondary, tertiary."""
    triple = COLOR_TRIPLE.get(base, (3, 7))
    mod = i % 3
    if mod == 0:
        return base
    elif mod == 1:
        return triple[0]
    else:
        return triple[1]

# 8 explosion directions (dx, dy)
DIR_X = [2, -2, 0, 0, 1, -1, 1, -1]
DIR_Y = [0, 0, 2, -2, 1, 1, -1, -1]
NUM_PARTICLES = 8

# Pre-allocate 3 firework slots
# Each slot: [phase, x, y, target_y, color, age,
#             px0,py0, px1,py1, px2,py2, px3,py3,
#             px4,py4, px5,py5, px6,py6, px7,py7]
# phase: 0=inactive, 1=launch, 2=explode, 3=fade
MAX_FW = 3
SLOT_SIZE = 6 + NUM_PARTICLES * 2
fw_slots = []
for _ in range(MAX_FW):
    fw_slots.append([0] * SLOT_SIZE)

def spawn_firework():
    """Find an inactive slot and launch a firework."""
    for s in fw_slots:
        if s[0] == 0:  # inactive
            s[0] = 1  # phase = launch
            s[1] = random.randint(5, WIDTH - 5)  # x
            s[2] = HEIGHT - 1  # y
            s[3] = random.randint(4, 14)  # target_y
            s[4] = random.choice(FIREWORK_COLORS)  # color
            s[5] = 0  # age
            return

def update_fireworks():
    """Update all firework slots."""
    for s in fw_slots:
        phase = s[0]
        if phase == 0:
            continue

        x = s[1]
        color = s[4]

        if phase == 1:  # launch
            # Erase old position
            set_pixel(x, s[2], 0)
            # Erase trail (1 pixel below)
            set_pixel(x, s[2] + 2, 0)

            # Move up
            s[2] -= 2

            if s[2] <= s[3]:
                # Explode! Initialize particles at burst point
                s[0] = 2  # phase = explode
                s[5] = 0  # age
                bx, by = x, s[2]
                for i in range(NUM_PARTICLES):
                    s[6 + i * 2] = bx
                    s[6 + i * 2 + 1] = by
            else:
                # Draw rocket + trail
                set_pixel(x, s[2], color)
                set_pixel(x, s[2] + 2, color)

        elif phase == 2:  # explode
            s[5] += 1
            age = s[5]

            # Erase old particles
            for i in range(NUM_PARTICLES):
                px = s[6 + i * 2]
                py = s[6 + i * 2 + 1]
                set_pixel(px, py, 0)

            if age <= 4:
                # Move particles outward
                for i in range(NUM_PARTICLES):
                    s[6 + i * 2] += DIR_X[i]
                    s[6 + i * 2 + 1] += DIR_Y[i]

                # Draw particles with color variation
                for i in range(NUM_PARTICLES):
                    px = s[6 + i * 2]
                    py = s[6 + i * 2 + 1]
                    set_pixel(px, py, particle_color(color, i))
            else:
                s[0] = 3  # phase = fade
                s[5] = 0

        elif phase == 3:  # fade
            s[5] += 1

            # Erase old particles
            for i in range(NUM_PARTICLES):
                px = s[6 + i * 2]
                py = s[6 + i * 2 + 1]
                set_pixel(px, py, 0)

            if s[5] <= 6:
                # Drift particles down
                for i in range(NUM_PARTICLES):
                    s[6 + i * 2 + 1] += 1

                # Draw with color variation
                for i in range(NUM_PARTICLES):
                    px = s[6 + i * 2]
                    py = s[6 + i * 2 + 1]
                    set_pixel(px, py, particle_color(color, i))
            else:
                # Done — mark inactive
                s[0] = 0

# ---------------------------------------------------------------
# Text positioning
# ---------------------------------------------------------------
# "HAPPY" on line 1, "NEW YEAR!" on line 2
# But we want the text to not get overwritten by fireworks,
# so we'll redraw it each frame.

happy_w = measure_word("HAPPY", 2)
happy_x = (WIDTH - happy_w) // 2

newyear_w = measure_word("NEW YEAR!", 2)
newyear_x = (WIDTH - newyear_w) // 2

# Use "2026" — update the year as needed
year_w = measure_word("2026", 2)
year_x = (WIDTH - year_w) // 2

def draw_text():
    """Draw the centered text."""
    draw_word(happy_x, 5, "HAPPY", 3, 2)
    draw_word(newyear_x, 16, "NEW YEAR!", 2, 2)

# Initial draw
draw_text()

# ---------------------------------------------------------------
# Main animation loop
# ---------------------------------------------------------------
print("Happy New Year! Display is running.")

spawn_timer = 0
SPAWN_INTERVAL = 8  # frames between new fireworks (~0.8 sec)

while True:
    # Spawn new fireworks periodically
    spawn_timer += 1
    if spawn_timer >= SPAWN_INTERVAL:
        spawn_timer = 0
        spawn_firework()

    # Update firework animations
    update_fireworks()

    # Redraw text over any firework debris
    draw_text()

    time.sleep(0.1)
