# Created by Kevin Wang - https://github.com/kwwangkw/
# modes/valentines.py - Valentine's Day banner mode (from Holidays/Valentines/code.py)
import random

WIDTH = 128
HEIGHT = 32
_bitmap = None

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

# Heart shapes - exact from original
BIG_HEART = [
    ".XX.XX.",
    "XXXXXXX",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "...X...",
]

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

# Text - exact glyphs from original
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'V': ["X...X","X...X","X...X","X...X",".X.X.",".X.X.","..X.."],
    'L': ["X....","X....","X....","X....","X....","X....","XXXXX"],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
    'N': ["X...X","XX..X","X.X.X","X.X.X","X..XX","X...X","X...X"],
    'T': ["XXXXX","..X..","..X..","..X..","..X..","..X..","..X.."],
    'I': ["XXXXX","..X..","..X..","..X..","..X..","..X..","XXXXX"],
    'S': [".XXX.","X...X","X....",".XXX.","....X","X...X",".XXX."],
    'D': ["XXXX.","X...X","X...X","X...X","X...X","X...X","XXXX."],
    '\'': ["..X..","..X..",".....",".....",".....",".....","....."],
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

# Floating hearts - from original (float upward)
NUM_HEARTS = 8
HEART_COLORS = [1, 1, 2, 2, 4, 5, 6, 7]
_hearts = None  # flat: [x, y, speed, color, small] * NUM_HEARTS

def edge_x():
    if random.randint(0, 1) == 0:
        return random.randint(0, 30)
    else:
        return random.randint(95, WIDTH - 7)

# Text positions
_l1_x = 0
_l2_x = 0


def setup(bitmap, palette):
    global _bitmap, _hearts, _l1_x, _l2_x
    _bitmap = bitmap

    # Exact palette from original
    palette[0] = 0x000000  # black
    palette[1] = 0x080000  # red (hearts)
    palette[2] = 0x080008  # pink
    palette[3] = 0x080808  # white (text)
    palette[4] = 0x100000  # bright red
    palette[5] = 0x080010  # magenta
    palette[6] = 0x100008  # hot pink
    palette[7] = 0x080800  # orange-ish

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Text layout from original: 2 lines
    line1 = "HAPPY"
    line2 = "VALENTINE'S"
    _l1_x = (WIDTH - measure_word(line1, 2)) // 2
    _l2_x = (WIDTH - measure_word(line2, 2)) // 2
    _draw_text()

    # Initialize hearts
    _hearts = [0] * (NUM_HEARTS * 5)
    for i in range(NUM_HEARTS):
        b = i * 5
        _hearts[b] = edge_x()                            # x
        _hearts[b + 1] = random.randint(0, HEIGHT - 1)   # y
        _hearts[b + 2] = random.choice([1, 1, 2])        # speed
        _hearts[b + 3] = random.choice(HEART_COLORS)     # color
        _hearts[b + 4] = random.randint(0, 1)            # small


def _draw_text():
    draw_word(_l1_x, 5, "HAPPY", 3, 2)
    draw_word(_l2_x, 16, "VALENTINE'S", 1, 2)


def animate(bitmap):
    # Update hearts - float upward like original
    for i in range(NUM_HEARTS):
        b = i * 5
        sm = _hearts[b + 4]
        # Erase old
        erase_heart(_hearts[b], _hearts[b + 1], sm)
        # Move up
        _hearts[b + 1] -= _hearts[b + 2]
        # Slight drift
        if random.randint(0, 4) == 0:
            _hearts[b] += random.choice([-1, 1])
            if _hearts[b] < 0:
                _hearts[b] = 0
            if _hearts[b] > WIDTH - 5:
                _hearts[b] = WIDTH - 5
        # Wrap at top
        if _hearts[b + 1] < -6:
            _hearts[b + 1] = HEIGHT
            _hearts[b] = edge_x()
            _hearts[b + 3] = random.choice(HEART_COLORS)
            _hearts[b + 4] = random.randint(0, 1)
        # Draw
        draw_heart(_hearts[b], _hearts[b + 1], _hearts[b + 3], _hearts[b + 4])

    _draw_text()

    return 0.15
