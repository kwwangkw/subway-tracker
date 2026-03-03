# modes/thanksgiving.py - Thanksgiving banner mode
import random

WIDTH = 128
HEIGHT = 32
_bitmap = None

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

# Leaf shapes
LEAF1 = [".X.X.X.","XXXXXXX",".XXXXX.","..XXX..","..XY...","...Y...","....Y.."]
LEAF2 = ["..XX..","..XXXX.",".XXXX.","XXXXX.",".XXXXX","..YX..","..Y..."]
LEAF3 = ["..X..","..XX..",".XXX.","XXXX.","XXXXX",".XY..","..Y.."]
LEAF4 = [".X..","XXX.",".XXX",".YX.","Y..."]
LEAF5 = [".XXX.","XXXXX","XXXX.",".XXX.","..Y..",".Y..."]
LEAF6 = ["XX.","XXX",".XX",".Y."]
LEAVES = [LEAF1, LEAF2, LEAF3, LEAF4, LEAF5, LEAF6]

STEM_COLOR = {1:5, 2:6, 3:5, 5:6, 8:5, 9:6, 10:6}
LEAF_COLORS = [1, 2, 3, 5, 8, 9, 10]
NUM_SHAPES = len(LEAVES)

_text_pixels = set()

def draw_leaf(x, y, color, shape):
    pattern = LEAVES[shape]
    vein = STEM_COLOR.get(color, 6)
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c == 'X':
                px, py = x + col, y + row
                if (px, py) not in _text_pixels:
                    set_pixel(px, py, color)
            elif c == 'Y':
                px, py = x + col, y + row
                if (px, py) not in _text_pixels:
                    set_pixel(px, py, vein)

def erase_leaf(x, y, shape):
    pattern = LEAVES[shape]
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c in ('X', 'Y'):
                px, py = x + col, y + row
                if (px, py) not in _text_pixels:
                    set_pixel(px, py, 0)

# Text
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'T': ["XXXXX","..X..","..X..","..X..","..X..","..X..","..X.."],
    'N': ["X...X","XX..X","X.X.X","X.X.X","X..XX","X...X","X...X"],
    'K': ["X...X","X..X.","X.X..","XX...","X.X..","X..X.","X...X"],
    'S': [".XXX.","X...X","X....",".XXX.","....X","X...X",".XXX."],
    'G': [".XXX.","X...X","X....","X.XXX","X...X","X...X",".XXX."],
    'I': ["XXXXX","..X..","..X..","..X..","..X..","..X..","XXXXX"],
    'V': ["X...X","X...X","X...X","X...X",".X.X.",".X.X.","..X.."],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
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
            w += 3; continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            w += 4; continue
        w += len(glyph[0]) + spacing
    return w - spacing

def draw_word(x, y, word, color, spacing=1):
    cursor = x
    for ch in word:
        if ch == ' ':
            cursor += 3; continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            cursor += 4; continue
        draw_letter(cursor, y, ch, color)
        cursor += len(ALPHA[ch][0]) + spacing

# Leaves
NUM_LEAVES = 10
FIELDS = 6
_leaves = None
_last_px = None
_last_py = None

def edge_x():
    if random.randint(0, 1) == 0:
        return random.randint(0, 30)
    return random.randint(95, WIDTH - 7)

def any_x():
    return random.randint(0, WIDTH - 7)

def rand_speed_y():
    return random.randint(4, 10)

def rand_speed_x():
    return random.choice([-2, -1, 0, 1, 1, 2])

_l1_x = 0
_l2_x = 0

def setup(bitmap, palette):
    global _bitmap, _leaves, _last_px, _last_py, _text_pixels, _l1_x, _l2_x
    _bitmap = bitmap

    palette[0] = 0x000000
    palette[1] = 0x100800   # bright orange
    palette[2] = 0x100000   # bright red
    palette[3] = 0x080800   # yellow
    palette[4] = 0x080808   # white
    palette[5] = 0x080400   # dim orange
    palette[6] = 0x080000   # dim red
    palette[7] = 0x100800
    palette[8] = 0x080800   # gold-yellow
    palette[9] = 0x180800   # red-orange
    palette[10] = 0x100000  # crimson

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    _l1_x = (WIDTH - measure_word("HAPPY", 2)) // 2
    _l2_x = (WIDTH - measure_word("THANKSGIVING", 2)) // 2
    draw_word(_l1_x, 5, "HAPPY", 4, 2)
    draw_word(_l2_x, 16, "THANKSGIVING", 1, 2)

    _text_pixels = set()
    for word, wx, wy, sp in [("HAPPY", _l1_x, 5, 2), ("THANKSGIVING", _l2_x, 16, 2)]:
        cursor = wx
        for ch in word:
            if ch == ' ':
                cursor += 3; continue
            glyph = ALPHA.get(ch)
            if glyph is None:
                cursor += 4; continue
            w = len(glyph[0]) if glyph else 3
            for row, line in enumerate(glyph):
                for col, c in enumerate(line):
                    if c == 'X':
                        px, py = cursor + col, wy + row
                        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                            _text_pixels.add((px, py))
            cursor += w + sp

    _leaves = [0] * (NUM_LEAVES * FIELDS)
    _last_px = [0] * NUM_LEAVES
    _last_py = [0] * NUM_LEAVES
    for i in range(NUM_LEAVES):
        b = i * FIELDS
        _leaves[b] = (edge_x() if random.randint(0, 4) != 0 else any_x()) * 10
        _leaves[b + 1] = random.randint(-HEIGHT, HEIGHT - 1) * 10
        _leaves[b + 2] = rand_speed_x()
        _leaves[b + 3] = rand_speed_y()
        _leaves[b + 4] = random.choice(LEAF_COLORS)
        _leaves[b + 5] = random.randint(0, NUM_SHAPES - 1)


def animate(bitmap):
    for i in range(NUM_LEAVES):
        b = i * FIELDS
        shape = _leaves[b + 5]
        old_px = _last_px[i]
        old_py = _last_py[i]
        _leaves[b] += _leaves[b + 2]
        _leaves[b + 1] += _leaves[b + 3]
        if random.randint(0, 15) == 0:
            _leaves[b + 2] = rand_speed_x()
        if _leaves[b] < 0:
            _leaves[b] = 0
        if _leaves[b] > (WIDTH - 7) * 10:
            _leaves[b] = (WIDTH - 7) * 10
        new_px = _leaves[b] // 10
        new_py = _leaves[b + 1] // 10
        if new_py > HEIGHT + 4:
            _leaves[b + 1] = random.randint(-12, -5) * 10
            _leaves[b] = (edge_x() if random.randint(0, 4) != 0 else any_x()) * 10
            _leaves[b + 2] = rand_speed_x()
            _leaves[b + 3] = rand_speed_y()
            _leaves[b + 4] = random.choice(LEAF_COLORS)
            _leaves[b + 5] = random.randint(0, NUM_SHAPES - 1)
            new_px = _leaves[b] // 10
            new_py = _leaves[b + 1] // 10
            erase_leaf(old_px, old_py, shape)
            _last_px[i] = new_px
            _last_py[i] = new_py
            continue
        if new_px != old_px or new_py != old_py:
            erase_leaf(old_px, old_py, shape)
            draw_leaf(new_px, new_py, _leaves[b + 4], _leaves[b + 5])
            _last_px[i] = new_px
            _last_py[i] = new_py

    return 0.05
