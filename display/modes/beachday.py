# Created by Kevin Wang - https://github.com/kwwangkw/
# modes/beachday.py - Beach Day banner mode (from Holidays/BeachDay/code.py)
import math

WIDTH = 128
HEIGHT = 32
_bitmap = None

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

def fill_rect(x, y, w, h, c):
    for dy in range(h):
        for dx in range(w):
            set_pixel(x + dx, y + dy, c)

# Text - exact glyphs from original
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'B': ["XXXX.","X...X","X...X","XXXX.","X...X","X...X","XXXX."],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
    'C': [".XXX.","X...X","X....","X....","X....","X...X",".XXX."],
    'D': ["XXXX.","X...X","X...X","X...X","X...X","X...X","XXXX."],
    '!': ["..X..","..X..","..X..","..X..","..X..",".....","..X.."],
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
            cursor += 3; continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            cursor += 4; continue
        w = len(glyph[0]) if glyph else 3
        draw_letter(cursor, y, ch, color)
        cursor += w + spacing

def measure_word(word, spacing=1):
    w = 0
    for ch in word:
        if ch == ' ':
            w += 3; continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            w += 4; continue
        w += len(glyph[0]) + spacing
    return w - spacing

# Scene layout from original
SAND_TOP = 28
WAVE_TOP = 25
WAVE_ROWS = 3

# Sun - from original (filled circle + rays)
SUN_CX = 112
SUN_CY = 7
SUN_R = 4

def draw_sun():
    for dy in range(-SUN_R, SUN_R + 1):
        for dx in range(-SUN_R, SUN_R + 1):
            if dx * dx + dy * dy <= SUN_R * SUN_R:
                set_pixel(SUN_CX + dx, SUN_CY + dy, 2)
    rays = [
        (0, -1), (0, 1), (-1, 0), (1, 0),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
    ]
    for rdx, rdy in rays:
        for dist in range(SUN_R + 1, SUN_R + 3):
            set_pixel(SUN_CX + rdx * dist, SUN_CY + rdy * dist, 2)

# Umbrellas - from original (semicircle dome canopy)
UMBRELLAS = [
    (20, 4, 5),    # red/white
    (64, 8, 5),    # blue/white
    (106, 9, 5),   # green/white
]
POLE_XS = [u[0] for u in UMBRELLAS]

def draw_umbrella(base_x, canopy_c, stripe_c):
    pole_top_y = SAND_TOP - 8
    for y in range(pole_top_y, SAND_TOP + 1):
        set_pixel(base_x, y, 10)
    R = 6
    cy_center = pole_top_y - 1
    for dy in range(-R, 1):
        for dx in range(-R, R + 1):
            if dx * dx + dy * dy <= R * R:
                cx = base_x + dx
                cy = cy_center + dy
                if (dx // 3) % 2 == 0:
                    set_pixel(cx, cy, canopy_c)
                else:
                    set_pixel(cx, cy, stripe_c)

# Waves - from original (3 rows with sine patterns)
_wave_offset = 0

def draw_waves(offset):
    for row in range(WAVE_ROWS):
        wy = WAVE_TOP + row
        for x in range(WIDTH):
            if x in POLE_XS:
                continue
            phase = (x + offset + row * 4) * 0.15
            val = math.sin(phase)
            if row == 0:
                if val > 0.5:
                    set_pixel(x, wy, 5)   # white foam
                elif val > 0.0:
                    set_pixel(x, wy, 7)   # cyan crest
                else:
                    set_pixel(x, wy, 6)   # darker blue
            elif row == 1:
                if val > 0.3:
                    set_pixel(x, wy, 7)
                else:
                    set_pixel(x, wy, 6)
            else:
                if val > 0.6:
                    set_pixel(x, wy, 7)
                else:
                    set_pixel(x, wy, 6)

# Text position
_text_x = 0


def setup(bitmap, palette):
    global _bitmap, _wave_offset, _text_x
    _bitmap = bitmap

    # Exact palette from original
    palette[0]  = 0x000000  # black
    palette[1]  = 0x000000  # unused
    palette[2]  = 0x080800  # yellow (sun / text)
    palette[3]  = 0x080800  # sand (same yellow)
    palette[4]  = 0x080000  # red (umbrella 1)
    palette[5]  = 0x080808  # white (wave foam / umbrella stripes)
    palette[6]  = 0x000008  # medium blue (wave dark)
    palette[7]  = 0x000808  # cyan / teal (wave crest)
    palette[8]  = 0x000008  # blue (umbrella 2)
    palette[9]  = 0x000800  # green (umbrella 3)
    palette[10] = 0x080000  # dark sand / pole

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Draw sand
    for y in range(SAND_TOP, HEIGHT):
        for x in range(WIDTH):
            set_pixel(x, y, 3)

    # Draw sun
    draw_sun()

    # Draw umbrellas
    for base_x, cc, sc in UMBRELLAS:
        draw_umbrella(base_x, cc, sc)

    # Draw initial waves
    draw_waves(0)

    # Text: single line from original
    line1 = "BEACH DAY!"
    _text_x = (WIDTH - measure_word(line1, 2)) // 2
    draw_word(_text_x, 7, line1, 2, 2)  # yellow

    _wave_offset = 0


def animate(bitmap):
    global _wave_offset
    _wave_offset += 1
    draw_waves(_wave_offset)

    return 0.12
