# Created by Kevin Wang - https://github.com/kwwangkw/
# modes/christmas.py - Christmas banner mode
import random

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

def draw_hline(x, y, w, c):
    for dx in range(w):
        set_pixel(x + dx, y, c)

def draw_vline(x, y, h, c):
    for dy in range(h):
        set_pixel(x, y + dy, c)

# Trees
def draw_tree(tx, ty, c_tree, c_trunk):
    set_pixel(tx, ty, c_tree)
    draw_hline(tx - 1, ty + 1, 3, c_tree)
    draw_hline(tx - 2, ty + 2, 5, c_tree)
    draw_hline(tx - 3, ty + 3, 7, c_tree)
    draw_hline(tx - 2, ty + 4, 5, c_tree)
    draw_hline(tx - 3, ty + 5, 7, c_tree)
    draw_hline(tx - 4, ty + 6, 9, c_tree)
    draw_hline(tx - 5, ty + 7, 11, c_tree)
    draw_hline(tx - 3, ty + 8, 7, c_tree)
    draw_hline(tx - 4, ty + 9, 9, c_tree)
    draw_hline(tx - 5, ty + 10, 11, c_tree)
    draw_hline(tx - 6, ty + 11, 13, c_tree)
    fill_rect(tx - 1, ty + 12, 3, 2, c_trunk)

def draw_small_tree(tx, ty, c_tree, c_trunk):
    set_pixel(tx, ty, c_tree)
    draw_hline(tx - 1, ty + 1, 3, c_tree)
    draw_hline(tx - 2, ty + 2, 5, c_tree)
    draw_hline(tx - 1, ty + 3, 3, c_tree)
    draw_hline(tx - 2, ty + 4, 5, c_tree)
    draw_hline(tx - 3, ty + 5, 7, c_tree)
    draw_hline(tx - 2, ty + 6, 5, c_tree)
    draw_hline(tx - 3, ty + 7, 7, c_tree)
    draw_hline(tx - 4, ty + 8, 9, c_tree)
    fill_rect(tx - 1, ty + 9, 3, 2, c_trunk)

BIG_TREE_LIGHTS = [
    (0,1),(-1,2),(1,2),(-2,3),(2,3),(0,5),(-3,6),(3,6),
    (-2,7),(2,7),(-1,9),(1,9),(-4,10),(0,10),(4,10),(-3,11),(3,11),
]
SMALL_TREE_LIGHTS = [
    (0,1),(-1,2),(1,2),(0,4),(-2,5),(2,5),(-1,7),(1,7),(-3,8),(0,8),(3,8),
]
LIGHT_COLORS = [1, 4, 5, 6]

def draw_tree_lights(tx, ty, frame, lights):
    for i, (lx, ly) in enumerate(lights):
        color_idx = (i + frame) % len(LIGHT_COLORS)
        set_pixel(tx + lx, ty + ly, LIGHT_COLORS[color_idx])

# Snow
NUM_SNOWFLAKES = 18
_snowflakes = []

def update_snowflakes():
    for sf in _snowflakes:
        set_pixel(sf[0], sf[1], 0)
        sf[1] += sf[0] % 2 + 1
        if random.randint(0, 3) == 0:
            sf[0] += random.choice([-1, 1])
            sf[0] = sf[0] % WIDTH
        if sf[1] >= HEIGHT:
            sf[1] = 0
            sf[0] = random.randint(0, WIDTH - 1)

def draw_snowflakes(c):
    for sf in _snowflakes:
        set_pixel(sf[0], sf[1], c)

# Text
ALPHA = {
    'M': ["X...X","XX.XX","X.X.X","X.X.X","X...X","X...X","X...X"],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
    'R': ["XXXX.","X...X","X...X","XXXX.","X..X.","X...X","X...X"],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'C': [".XXX.","X...X","X....","X....","X....","X...X",".XXX."],
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'I': ["XXXXX","..X..","..X..","..X..","..X..","..X..","XXXXX"],
    'S': [".XXX.","X...X","X....",".XXX.","....X","X...X",".XXX."],
    'T': ["XXXXX","..X..","..X..","..X..","..X..","..X..","..X.."],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
}

def draw_letter(x, y, ch, color):
    glyph = ALPHA.get(ch)
    if glyph is None:
        return
    for row, line in enumerate(glyph):
        for col, c in enumerate(line):
            if c == 'X':
                set_pixel(x + col, y + row, color)

def measure_word(word, spacing=1):
    w = 0
    for ch in word:
        if ch == ' ':
            w += 2; continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            w += 4; continue
        w += len(glyph[0]) + spacing
    return w - spacing

def draw_word(x, y, word, color, spacing=1):
    cursor = x
    for ch in word:
        if ch == ' ':
            cursor += 2; continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            cursor += 4; continue
        draw_letter(cursor, y, ch, color)
        cursor += len(ALPHA[ch][0]) + spacing

# Tree positions
TREES = [
    (14, 18, True), (5, 21, False), (113, 18, True),
    (122, 21, False), (27, 21, False), (100, 21, False),
]

_frame = 0
_light_timer = 0
_merry_x = 0
_christmas_x = 0


def setup(bitmap, palette):
    global _bitmap, _frame, _light_timer, _snowflakes, _merry_x, _christmas_x
    _bitmap = bitmap
    _frame = 0
    _light_timer = 0

    palette[0] = 0x000000
    palette[1] = 0x080000  # red
    palette[2] = 0x000800  # green
    palette[3] = 0x080808  # white
    palette[4] = 0x080800  # yellow
    palette[5] = 0x000008  # blue
    palette[6] = 0x000800  # green

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Trees
    for tx, ty, big in TREES:
        if big:
            draw_tree(tx, ty, 2, 1)
        else:
            draw_small_tree(tx, ty, 2, 1)
        set_pixel(tx, ty - 1, 4)

    # Snow
    _snowflakes = []
    for _ in range(NUM_SNOWFLAKES):
        _snowflakes.append([random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1), 0])

    # Text
    _merry_x = (WIDTH - measure_word("MERRY", 2)) // 2
    _christmas_x = (WIDTH - measure_word("CHRISTMAS", 2)) // 2
    draw_word(_merry_x, 6, "MERRY", 3, 2)
    draw_word(_christmas_x, 16, "CHRISTMAS", 1, 2)

    draw_snowflakes(3)


def animate(bitmap):
    global _frame, _light_timer

    update_snowflakes()
    draw_snowflakes(3)

    _light_timer += 1
    if _light_timer >= 5:
        _light_timer = 0
        _frame += 1

    for tx, ty, big in TREES:
        if big:
            draw_tree(tx, ty, 2, 1)
        else:
            draw_small_tree(tx, ty, 2, 1)
        lights = BIG_TREE_LIGHTS if big else SMALL_TREE_LIGHTS
        draw_tree_lights(tx, ty, _frame, lights)
        set_pixel(tx, ty - 1, 4)

    draw_word(_merry_x, 6, "MERRY", 3, 2)
    draw_word(_christmas_x, 16, "CHRISTMAS", 1, 2)

    return 0.1
