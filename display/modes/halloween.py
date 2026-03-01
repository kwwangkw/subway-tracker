# modes/halloween.py — Halloween banner mode
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

def draw_hline(x, y, w, c):
    for dx in range(w):
        set_pixel(x + dx, y, c)

def draw_vline(x, y, h, c):
    for dy in range(h):
        set_pixel(x, y + dy, c)

# Spider
def draw_spider(sx, sy, c):
    draw_vline(sx, 0, sy, c)
    fill_rect(sx - 1, sy, 2, 1, c)
    fill_rect(sx - 1, sy + 1, 3, 3, c)
    set_pixel(sx - 3, sy + 1, c); set_pixel(sx - 4, sy, c)
    set_pixel(sx - 3, sy + 2, c); set_pixel(sx - 4, sy + 3, c)
    set_pixel(sx - 3, sy + 3, c); set_pixel(sx - 4, sy + 2, c)
    set_pixel(sx + 3, sy + 1, c); set_pixel(sx + 4, sy, c)
    set_pixel(sx + 3, sy + 2, c); set_pixel(sx + 4, sy + 3, c)
    set_pixel(sx + 3, sy + 3, c); set_pixel(sx + 4, sy + 2, c)

def clear_spider(sx, sy):
    draw_spider(sx, sy, 0)

# Bat
def draw_bat(bx, by, c):
    set_pixel(bx, by, c); set_pixel(bx, by + 1, c)
    set_pixel(bx - 1, by, c); set_pixel(bx - 2, by - 1, c)
    set_pixel(bx - 3, by - 1, c); set_pixel(bx - 4, by, c)
    set_pixel(bx - 3, by + 1, c)
    set_pixel(bx + 1, by, c); set_pixel(bx + 2, by - 1, c)
    set_pixel(bx + 3, by - 1, c); set_pixel(bx + 4, by, c)
    set_pixel(bx + 3, by + 1, c)
    set_pixel(bx - 1, by - 1, c); set_pixel(bx + 1, by - 1, c)

def clear_bat(bx, by):
    draw_bat(bx, by, 0)

# Text
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'L': ["X....","X....","X....","X....","X....","X....","XXXXX"],
    'O': [".XXX.","X...X","X...X","X...X","X...X","X...X",".XXX."],
    'W': ["X...X","X...X","X...X","X.X.X","X.X.X","XX.XX","X...X"],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
    'N': ["X...X","XX..X","XX..X","X.X.X","X..XX","X..XX","X...X"],
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
        w = len(glyph[0]) if glyph else 3
        draw_letter(cursor, y, ch, color)
        cursor += w + spacing

# Animation state
S1_X, S1_MIN, S1_MAX = 10, 9, 13
S2_X, S2_MIN, S2_MAX = 20, 19, 25
B1_X, B1_MIN, B1_MAX = 40, 2, 5
B2_X, B2_MIN, B2_MAX = 90, 3, 6

_frame = 0
_s1_prev = S1_MIN
_s2_prev = S2_MIN
_b1_prev = B1_MIN
_b2_prev = B2_MIN
_tail_prev = 0

# Cat position
_cx, _cy = 113, 24

TAIL_POSES = [
    [(117, 31), (118, 30), (119, 29), (120, 28), (120, 27)],
    [(117, 31), (118, 30), (119, 29), (120, 29), (120, 28)],
    [(117, 31), (118, 31), (119, 30), (120, 29), (120, 28)],
]

def draw_tail(pose_idx, c):
    for (tx, ty) in TAIL_POSES[pose_idx]:
        set_pixel(tx, ty, c)

def clear_tail(pose_idx):
    draw_tail(pose_idx, 0)


def setup(bitmap, palette):
    global _bitmap, _frame, _s1_prev, _s2_prev, _b1_prev, _b2_prev, _tail_prev
    _bitmap = bitmap
    _frame = 0
    _s1_prev = S1_MIN
    _s2_prev = S2_MIN
    _b1_prev = B1_MIN
    _b2_prev = B2_MIN
    _tail_prev = 0

    palette[0] = 0x000000
    palette[1] = 0x280C00  # orange

    # Clear
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Cobweb
    draw_hline(118, 0, 10, 1)
    draw_vline(127, 0, 10, 1)
    for i in range(8):
        set_pixel(127 - i, i, 1)
    for px, py in [(125,0),(126,1),(127,2),(122,0),(123,1),(124,1),(125,2),
                   (126,3),(127,4),(126,4),(119,0),(120,1),(121,1),(122,2),
                   (123,3),(124,3),(125,4),(126,5),(126,6),(127,7),(127,8)]:
        set_pixel(px, py, 1)

    # Cat
    cx, cy = _cx, _cy
    fill_rect(cx, cy + 2, 4, 6, 1)
    fill_rect(cx, cy, 3, 3, 1)
    set_pixel(cx, cy - 1, 1); set_pixel(cx + 2, cy - 1, 1)
    draw_vline(cx, cy + 8, 2, 1); draw_vline(cx + 1, cy + 8, 2, 1)
    draw_vline(cx + 3, cy + 8, 2, 1)

    # Text
    happy_w = measure_word("HAPPY", 2)
    happy_x = (WIDTH - happy_w) // 2
    draw_word(happy_x, 8, "HAPPY", 1, 2)
    halloween_w = measure_word("HALLOWEEN", 2)
    halloween_x = (WIDTH - halloween_w) // 2
    draw_word(halloween_x, 18, "HALLOWEEN", 1, 2)

    # Initial positions
    draw_spider(S1_X, _s1_prev, 1)
    draw_spider(S2_X, _s2_prev, 1)
    draw_bat(B1_X, _b1_prev, 1)
    draw_bat(B2_X, _b2_prev, 1)
    draw_tail(0, 1)


def animate(bitmap):
    global _frame, _s1_prev, _s2_prev, _b1_prev, _b2_prev, _tail_prev
    _frame += 1
    f = _frame

    s1_y = S1_MIN + int((math.sin(f * 0.10) + 1) / 2 * (S1_MAX - S1_MIN))
    s2_y = S2_MIN + int((math.sin(f * 0.08 + 2) + 1) / 2 * (S2_MAX - S2_MIN))
    b1_y = B1_MIN + int((math.sin(f * 0.12 + 1) + 1) / 2 * (B1_MAX - B1_MIN))
    b2_y = B2_MIN + int((math.sin(f * 0.14 + 3) + 1) / 2 * (B2_MAX - B2_MIN))
    tail_pose = int((math.sin(f * 0.07) + 1) / 2 * 2.99)

    if s1_y != _s1_prev:
        clear_spider(S1_X, _s1_prev); draw_spider(S1_X, s1_y, 1); _s1_prev = s1_y
    if s2_y != _s2_prev:
        clear_spider(S2_X, _s2_prev); draw_spider(S2_X, s2_y, 1); _s2_prev = s2_y
    if b1_y != _b1_prev:
        clear_bat(B1_X, _b1_prev); draw_bat(B1_X, b1_y, 1); _b1_prev = b1_y
    if b2_y != _b2_prev:
        clear_bat(B2_X, _b2_prev); draw_bat(B2_X, b2_y, 1); _b2_prev = b2_y
    if tail_pose != _tail_prev:
        clear_tail(_tail_prev); draw_tail(tail_pose, 1); _tail_prev = tail_pose

    return 0.1
