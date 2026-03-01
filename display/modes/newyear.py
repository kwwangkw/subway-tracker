# modes/newyear.py — New Year banner mode (from Holidays/NewYear/code.py)
import random

WIDTH = 128
HEIGHT = 32
_bitmap = None

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

# Text — exact glyphs from original
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'N': ["X...X","XX..X","X.X.X","X.X.X","X..XX","X...X","X...X"],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
    'W': ["X...X","X...X","X...X","X.X.X","X.X.X","XX.XX","X...X"],
    'R': ["XXXX.","X...X","X...X","XXXX.","X..X.","X...X","X...X"],
    '!': ["..X..","..X..","..X..","..X..","..X..",".....","..X.."],
    '2': [".XXX.","X...X","....X","..XX.",".X...","X....","XXXXX"],
    '0': [".XXX.","X...X","X..XX","X.X.X","XX..X","X...X",".XXX."],
    '6': [".XXX.","X....","X....","XXXX.","X...X","X...X",".XXX."],
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

# Fireworks — exact system from original
FIREWORK_COLORS = [1, 3, 4, 5, 6, 7]

COLOR_TRIPLE = {
    1: (6, 3),   # red -> magenta, white
    3: (7, 1),   # white -> cyan, red
    4: (7, 6),   # blue -> cyan, magenta
    5: (7, 3),   # green -> cyan, white
    6: (1, 4),   # magenta -> red, blue
    7: (4, 5),   # cyan -> blue, green
}

def particle_color(base, i):
    triple = COLOR_TRIPLE.get(base, (3, 7))
    mod = i % 3
    if mod == 0:
        return base
    elif mod == 1:
        return triple[0]
    else:
        return triple[1]

DIR_X = [2, -2, 0, 0, 1, -1, 1, -1]
DIR_Y = [0, 0, 2, -2, 1, 1, -1, -1]
NUM_PARTICLES = 8

MAX_FW = 3
SLOT_SIZE = 6 + NUM_PARTICLES * 2
_fw_slots = None

def spawn_firework():
    for s in _fw_slots:
        if s[0] == 0:
            s[0] = 1
            s[1] = random.randint(5, WIDTH - 5)
            s[2] = HEIGHT - 1
            s[3] = random.randint(4, 14)
            s[4] = random.choice(FIREWORK_COLORS)
            s[5] = 0
            return

def update_fireworks():
    for s in _fw_slots:
        phase = s[0]
        if phase == 0:
            continue
        x = s[1]
        color = s[4]

        if phase == 1:
            set_pixel(x, s[2], 0)
            set_pixel(x, s[2] + 2, 0)
            s[2] -= 2
            if s[2] <= s[3]:
                s[0] = 2
                s[5] = 0
                bx, by = x, s[2]
                for i in range(NUM_PARTICLES):
                    s[6 + i * 2] = bx
                    s[6 + i * 2 + 1] = by
            else:
                set_pixel(x, s[2], color)
                set_pixel(x, s[2] + 2, color)

        elif phase == 2:
            s[5] += 1
            for i in range(NUM_PARTICLES):
                set_pixel(s[6 + i * 2], s[6 + i * 2 + 1], 0)
            if s[5] <= 4:
                for i in range(NUM_PARTICLES):
                    s[6 + i * 2] += DIR_X[i]
                    s[6 + i * 2 + 1] += DIR_Y[i]
                for i in range(NUM_PARTICLES):
                    set_pixel(s[6 + i * 2], s[6 + i * 2 + 1],
                              particle_color(color, i))
            else:
                s[0] = 3
                s[5] = 0

        elif phase == 3:
            s[5] += 1
            for i in range(NUM_PARTICLES):
                set_pixel(s[6 + i * 2], s[6 + i * 2 + 1], 0)
            if s[5] <= 6:
                for i in range(NUM_PARTICLES):
                    s[6 + i * 2 + 1] += 1
                for i in range(NUM_PARTICLES):
                    set_pixel(s[6 + i * 2], s[6 + i * 2 + 1],
                              particle_color(color, i))
            else:
                s[0] = 0

# Text positions
_happy_x = 0
_newyear_x = 0
_spawn_timer = 0


def setup(bitmap, palette):
    global _bitmap, _fw_slots, _spawn_timer, _happy_x, _newyear_x
    _bitmap = bitmap

    # Exact palette from original
    palette[0] = 0x000000  # black
    palette[1] = 0x180000  # red
    palette[2] = 0x100800  # gold/orange
    palette[3] = 0x080808  # white (text)
    palette[4] = 0x000018  # blue
    palette[5] = 0x001800  # green
    palette[6] = 0x180010  # magenta/pink
    palette[7] = 0x001818  # cyan

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Text layout from original: 2 lines
    _happy_x = (WIDTH - measure_word("HAPPY", 2)) // 2
    _newyear_x = (WIDTH - measure_word("NEW YEAR!", 2)) // 2

    _draw_text()

    _fw_slots = []
    for _ in range(MAX_FW):
        _fw_slots.append([0] * SLOT_SIZE)
    _spawn_timer = 0


def _draw_text():
    draw_word(_happy_x, 5, "HAPPY", 3, 2)
    draw_word(_newyear_x, 16, "NEW YEAR!", 2, 2)


def animate(bitmap):
    global _spawn_timer
    _spawn_timer += 1
    if _spawn_timer >= 8:
        _spawn_timer = 0
        spawn_firework()

    update_fireworks()
    _draw_text()

    return 0.1
