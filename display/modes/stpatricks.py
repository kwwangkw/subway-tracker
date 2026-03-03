# modes/stpatricks.py - St Patrick's Day banner mode (from Holidays/StPatricks/code.py)
import random

WIDTH = 128
HEIGHT = 32
_bitmap = None

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

# Shamrock shapes - exact from original
SHAMROCK = [
    ".XX...XX.",
    "XXXX.XXXX",
    "XXXX.XXXX",
    ".XXXXXXX.",
    "...XXX...",
    ".XXXXXXX.",
    "XXXX.XXXX",
    "XXXX.XXXX",
    ".XX...XX.",
    "....X....",
    "...X.....",
]

SMALL_SHAMROCK = [
    "XX.XX",
    "XXXXX",
    ".XXX.",
    "XXXXX",
    "XX.XX",
    "..X..",
    ".X...",
]

def draw_shamrock(x, y, color, stem_color, small=False):
    pattern = SMALL_SHAMROCK if small else SHAMROCK
    for row, line in enumerate(pattern):
        for col, c in enumerate(line):
            if c == 'X':
                if small and row >= 5:
                    set_pixel(x + col, y + row, stem_color)
                elif not small and row >= 9:
                    set_pixel(x + col, y + row, stem_color)
                else:
                    set_pixel(x + col, y + row, color)

# Text - exact glyphs from original
ALPHA = {
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'S': [".XXX.","X...X","X....",".XXX.","....X","X...X",".XXX."],
    'T': ["XXXXX","..X..","..X..","..X..","..X..","..X..","..X.."],
    'R': ["XXXX.","X...X","X...X","XXXX.","X..X.","X...X","X...X"],
    'I': ["XXXXX","..X..","..X..","..X..","..X..","..X..","XXXXX"],
    'C': [".XXX.","X...X","X....","X....","X....","X...X",".XXX."],
    'K': ["X...X","X..X.","X.X..","XX...","X.X..","X..X.","X...X"],
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

# Floating shamrocks - from original (float upward)
NUM_SHAMS = 3
SHAM_COLORS = [1]
STEM_COLOR = 2
_shams = None  # flat: [x, y, speed, color, small] * NUM_SHAMS

def edge_x():
    if random.randint(0, 1) == 0:
        return random.randint(0, 30)
    else:
        return random.randint(95, WIDTH - 9)

# Text positions
_l1_x = 0
_l2_x = 0


def setup(bitmap, palette):
    global _bitmap, _shams, _l1_x, _l2_x
    _bitmap = bitmap

    # Exact palette from original
    palette[0] = 0x000000  # black
    palette[1] = 0x000800  # green (shamrocks/text)
    palette[2] = 0x000400  # dark green (stems)
    palette[3] = 0x080808  # white (text)
    palette[4] = 0x000C00  # bright green
    palette[5] = 0x080800  # yellow/gold
    palette[6] = 0x040400  # dim yellow
    palette[7] = 0x000800  # green

    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Text layout from original: 2 lines
    line1 = "HAPPY ST"
    line2 = "PATRICK'S DAY"
    _l1_x = (WIDTH - measure_word(line1, 2)) // 2
    _l2_x = (WIDTH - measure_word(line2, 2)) // 2
    _draw_text()

    # Initialize shamrocks
    _shams = [0] * (NUM_SHAMS * 5)
    for i in range(NUM_SHAMS):
        b = i * 5
        _shams[b] = edge_x()
        _shams[b + 1] = random.randint(0, HEIGHT + 5)
        _shams[b + 2] = random.choice([1, 1, 2])
        _shams[b + 3] = random.choice(SHAM_COLORS)
        _shams[b + 4] = random.randint(0, 1)


def _draw_text():
    draw_word(_l1_x, 5, "HAPPY ST", 3, 2)
    draw_word(_l2_x, 16, "PATRICK'S DAY", 1, 2)


def animate(bitmap):
    # Update shamrocks - float upward like original
    for i in range(NUM_SHAMS):
        b = i * 5
        sm = _shams[b + 4]
        old_x = _shams[b]
        old_y = _shams[b + 1]

        # Erase old position
        pattern = SMALL_SHAMROCK if sm else SHAMROCK
        for row, line in enumerate(pattern):
            for col, c in enumerate(line):
                if c == 'X':
                    px = old_x + col
                    py = old_y + row
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        _bitmap[px, py] = 0

        # Move upward
        _shams[b + 1] -= _shams[b + 2]
        if random.randint(0, 4) == 0:
            _shams[b] += random.choice([-1, 1])
            if _shams[b] < 0:
                _shams[b] = 0
            if _shams[b] > WIDTH - 5:
                _shams[b] = WIDTH - 5

        # Wrap at top
        if _shams[b + 1] < -11:
            _shams[b + 1] = HEIGHT + 2
            _shams[b] = edge_x()
            _shams[b + 3] = random.choice(SHAM_COLORS)
            _shams[b + 4] = random.randint(0, 1)
            sm = _shams[b + 4]

        # Draw new position
        draw_shamrock(_shams[b], _shams[b + 1], _shams[b + 3], 2, sm)

    _draw_text()

    return 0.15
