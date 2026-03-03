# modes/july4th.py - July 4th banner mode (from Holidays/July4th/code.py)
import random

WIDTH = 128
HEIGHT = 32
_bitmap = None

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

# Text - exact glyphs from original
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    '4': ["X...X","X...X","X...X","XXXXX","....X","....X","....X"],
    'T': ["XXXXX","..X..","..X..","..X..","..X..","..X..","..X.."],
    'O': [".XXX.","X...X","X...X","X...X","X...X","X...X",".XXX."],
    'F': ["XXXXX","X....","X....","XXX..","X....","X....","X...."],
    'J': ["XXXXX","....X","....X","....X","....X","X...X",".XXX."],
    'U': ["X...X","X...X","X...X","X...X","X...X","X...X",".XXX."],
    'L': ["X....","X....","X....","X....","X....","X....","XXXXX"],
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

# Fireworks - exact system from original
FIREWORK_COLORS = [1, 2, 3]  # red, white, blue
RWB = [1, 2, 3]

def particle_color(base, i):
    return RWB[i % 3]

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
            s[1] = random.randint(15, WIDTH - 15)
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
                set_pixel(x, s[2], 4)  # yellow rocket
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
_l1_x = 0
_fourth_x = 0
_l2_x = 0
_spawn_timer = 0


def setup(bitmap, palette):
    global _bitmap, _fw_slots, _spawn_timer, _l1_x, _fourth_x, _l2_x
    _bitmap = bitmap

    # Exact palette from original
    palette[0] = 0x000000  # black
    palette[1] = 0x080000  # red
    palette[2] = 0x080808  # white
    palette[3] = 0x000008  # blue (via green channel)
    palette[4] = 0x080800  # yellow (rocket trail)
    palette[5] = 0x040000  # dim red
    palette[6] = 0x000004  # dim blue
    palette[7] = 0x040404  # dim white

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Text layout from original: 2 lines
    line1 = "HAPPY 4TH"
    line2 = "OF JULY!"
    l1_w = measure_word(line1, 2)
    _l1_x = (WIDTH - l1_w) // 2
    l2_w = measure_word(line2, 2)
    _l2_x = (WIDTH - l2_w) // 2

    happy_w = measure_word("HAPPY", 2)
    _fourth_x = _l1_x + happy_w + 3  # 3px space

    _draw_text()

    _fw_slots = []
    for _ in range(MAX_FW):
        _fw_slots.append([0] * SLOT_SIZE)
    _spawn_timer = 0


def _draw_text():
    draw_word(_l1_x, 7, "HAPPY", 2, 2)      # white
    draw_word(_fourth_x, 7, "4TH", 3, 2)    # blue
    draw_word(_l2_x, 18, "OF JULY!", 1, 2)   # red


def animate(bitmap):
    global _spawn_timer
    _spawn_timer += 1
    if _spawn_timer >= 8:
        _spawn_timer = 0
        spawn_firework()

    update_fireworks()
    _draw_text()

    return 0.1
