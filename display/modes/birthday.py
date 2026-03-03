# Created by Kevin Wang - https://github.com/kwwangkw/
# modes/birthday.py - Happy Birthday banner mode
#
# Shows "HAPPY BIRTHDAY [NAME]!" with confetti animation.
# Name is passed in via setup(bitmap, palette, name="...").
import random

WIDTH = 128
HEIGHT = 32
_bitmap = None
_name = "FRIEND"

def set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c

def fill_rect(x, y, w, h, c):
    for dy in range(h):
        for dx in range(w):
            set_pixel(x + dx, y + dy, c)

# Gift box icon (11x13)
_GIFT = [
    "..XX...XX..",  # row 0:  bow loops
    ".X..X.X..X.",  # row 1:  bow loops
    ".X..XXX..X.",  # row 2:  bow loops
    "..XXXXXXX..",  # row 3:  bow base
    "XXXXXAXXXXX",  # row 4:  lid top
    "XXXXXAXXXXX",  # row 5:  lid bottom
    "XXXXXAXXXXX",  # row 6:  box body
    "XXXXXAXXXXX",  # row 7:  box body
    "XXXXXAXXXXX",  # row 8:  box body
    "XXXXXAXXXXX",  # row 9:  box body
    "XXXXXAXXXXX",  # row 10: box body
    "XXXXXAXXXXX",  # row 11: box body
    "XXXXXXXXXXX",  # row 12: box bottom
]

def _draw_gift(cx, cy):
    """Draw a gift box at position."""
    for row_i, row_str in enumerate(_GIFT):
        for col_i, ch in enumerate(row_str):
            if ch == "X":
                if row_i <= 3:
                    # Bow - yellow
                    set_pixel(cx + col_i, cy + row_i, 4)
                else:
                    # Box body - red
                    set_pixel(cx + col_i, cy + row_i, 1)
            elif ch == "A":
                # Ribbon stripe - yellow
                set_pixel(cx + col_i, cy + row_i, 4)

# Cake icon (11x14)
_CAKE = [
    "...X.X.X...",  # row 0:  candle flames
    "...X.X.X...",  # row 1:  candle sticks
    "...X.X.X...",  # row 2:  candle sticks
    "...X.X.X...",  # row 3:  candle sticks
    ".XXXXXXXXX.",  # row 4:  frosting
    ".XXXXXXXXX.",  # row 5:  frosting
    ".X.X.X.X.X.",  # row 6:  frosting drip
    ".XXXXXXXXX.",  # row 7:  cake body
    ".XXXXXXXXX.",  # row 8:  cake body
    ".XXXXXXXXX.",  # row 9:  cake body
    ".XXXXXXXXX.",  # row 10: cake body
    "XXXXXXXXXXX",  # row 11: plate
    "XXXXXXXXXXX",  # row 12: plate
    "XXXXXXXXXXX",  # row 13: plate
]

def _draw_cake(cx, cy):
    """Draw a birthday cake at position."""
    for row_i, row_str in enumerate(_CAKE):
        for col_i, ch in enumerate(row_str):
            if ch == "X":
                if row_i == 0:
                    set_pixel(cx + col_i, cy + row_i, random.choice([4, 5, 1]))
                elif row_i <= 3:
                    set_pixel(cx + col_i, cy + row_i, 3)   # white candles
                elif row_i <= 6:
                    set_pixel(cx + col_i, cy + row_i, 6)   # pink frosting
                elif row_i <= 10:
                    set_pixel(cx + col_i, cy + row_i, 7)   # tan cake body
                else:
                    set_pixel(cx + col_i, cy + row_i, 3)   # white plate

# Text glyphs (5x7 pixel art)
ALPHA = {
    'A': [".XXX.","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'B': ["XXXX.","X...X","X...X","XXXX.","X...X","X...X","XXXX."],
    'C': [".XXX.","X...X","X....","X....","X....","X...X",".XXX."],
    'D': ["XXXX.","X...X","X...X","X...X","X...X","X...X","XXXX."],
    'E': ["XXXXX","X....","X....","XXX..","X....","X....","XXXXX"],
    'F': ["XXXXX","X....","X....","XXX..","X....","X....","X...."],
    'G': [".XXX.","X...X","X....","X.XXX","X...X","X...X",".XXX."],
    'H': ["X...X","X...X","X...X","XXXXX","X...X","X...X","X...X"],
    'I': ["XXXXX","..X..","..X..","..X..","..X..","..X..","XXXXX"],
    'J': ["..XXX","....X","....X","....X","....X","X...X",".XXX."],
    'K': ["X...X","X..X.","X.X..","XX...","X.X..","X..X.","X...X"],
    'L': ["X....","X....","X....","X....","X....","X....","XXXXX"],
    'M': ["X...X","XX.XX","X.X.X","X.X.X","X...X","X...X","X...X"],
    'N': ["X...X","XX..X","X.X.X","X.X.X","X..XX","X...X","X...X"],
    'O': [".XXX.","X...X","X...X","X...X","X...X","X...X",".XXX."],
    'P': ["XXXX.","X...X","X...X","XXXX.","X....","X....","X...."],
    'Q': [".XXX.","X...X","X...X","X...X","X.X.X","X..X.",".XX.X"],
    'R': ["XXXX.","X...X","X...X","XXXX.","X..X.","X...X","X...X"],
    'S': [".XXX.","X...X","X....",".XXX.","....X","X...X",".XXX."],
    'T': ["XXXXX","..X..","..X..","..X..","..X..","..X..","..X.."],
    'U': ["X...X","X...X","X...X","X...X","X...X","X...X",".XXX."],
    'V': ["X...X","X...X","X...X","X...X",".X.X.",".X.X.","..X.."],
    'W': ["X...X","X...X","X...X","X.X.X","X.X.X","XX.XX","X...X"],
    'X': ["X...X",".X.X.",".X.X.","..X..",".X.X.",".X.X.","X...X"],
    'Y': ["X...X","X...X",".X.X.","..X..","..X..","..X..","..X.."],
    'Z': ["XXXXX","....X","...X.","..X..","..X..",".X...","XXXXX"],
    '!': ["..X..","..X..","..X..","..X..","..X..",".....","..X.."],
    ' ': ["....","....","....","....","....","....","...."],
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
            w += 3
            continue
        glyph = ALPHA.get(ch)
        if glyph is None:
            w += 4
            continue
        w += len(glyph[0]) + spacing
    return w - spacing

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
        draw_letter(cursor, y, ch, color)
        cursor += len(glyph[0]) + spacing

# Confetti
NUM_CONFETTI = 16
CONFETTI_COLORS = [1, 2, 4, 5, 6]
_confetti = []  # list of [x, y, speed, color]

def _init_confetti():
    global _confetti
    _confetti = []
    for _ in range(NUM_CONFETTI):
        _confetti.append([
            random.randint(0, WIDTH - 1),
            random.randint(0, HEIGHT - 1),
            random.randint(1, 2),
            random.choice(CONFETTI_COLORS),
        ])

def _update_confetti():
    for cf in _confetti:
        set_pixel(cf[0], cf[1], 0)  # erase old
        cf[1] += cf[2]  # fall down
        if random.randint(0, 2) == 0:
            cf[0] += random.choice([-1, 1])
            cf[0] = cf[0] % WIDTH
        if cf[1] >= HEIGHT:
            cf[1] = 0
            cf[0] = random.randint(0, WIDTH - 1)
            cf[2] = random.randint(1, 2)
            cf[3] = random.choice(CONFETTI_COLORS)

def _draw_confetti():
    for cf in _confetti:
        set_pixel(cf[0], cf[1], cf[3])

# Layout positions
_line1_x = 0
_line2_x = 0
_line1_y = 0
_line2_y = 0
_cake_x = 0
_gift_x = 0
_frame = 0


def setup(bitmap, palette, name=None, **kwargs):
    """Initialize birthday mode."""
    global _bitmap, _name, _line1_x, _line2_x, _line1_y, _line2_y, _cake_x, _gift_x, _frame
    _bitmap = bitmap
    if name is not None:
        _name = name.upper()
    else:
        _name = None
    _frame = 0

    # Palette
    palette[0] = 0x000000  # black
    palette[1] = 0x100000  # red
    palette[2] = 0x001000  # green
    palette[3] = 0x080808  # white
    palette[4] = 0x100800  # yellow
    palette[5] = 0x100008  # orange/magenta
    palette[6] = 0x080010  # pink
    palette[7] = 0x0C0604  # cake tan/brown

    # Clear
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Layout: cake on left, gift on right, text centered
    _cake_x = 8
    _gift_x = WIDTH - 8 - 11  # symmetric right side
    _draw_cake(_cake_x, 9)
    _draw_gift(_gift_x, 9)

    # "HAPPY BIRTHDAY" on line 1, name + "!" on line 2 (if name exists)
    text_start = 18  # after cake
    line1 = "HAPPY"
    line2 = "BIRTHDAY!"

    if _name is not None:
        line1 = "HAPPY BIRTHDAY"
        line2 = _name + "!"

    line1_w = measure_word(line1, 1)
    line2_w = measure_word(line2, 1)

    # Center text on the full display width
    _line1_x = (WIDTH - line1_w) // 2
    _line2_x = (WIDTH - line2_w) // 2

    # Two lines of 7px text with a gap, centered vertically on 32px display
    gap = 4
    total_h = 7 + gap + 7  # 18px
    _line1_y = (HEIGHT - total_h) // 2
    _line2_y = _line1_y + 7 + gap

    draw_word(_line1_x, _line1_y, line1, 4, 1)   # yellow
    draw_word(_line2_x, _line2_y, line2, 6, 1)    # pink

    # Confetti
    _init_confetti()
    _draw_confetti()


def animate(bitmap):
    """Animate confetti."""
    global _frame

    # Erase old confetti, move, then immediately draw at new positions
    _update_confetti()
    _draw_confetti()

    # Redraw all static elements on top of confetti (like Christmas trees over snow)
    _draw_cake(_cake_x, 9)
    _draw_gift(_gift_x, 9)

    _frame += 1

    if _name is not None:
        draw_word(_line1_x, _line1_y, "HAPPY BIRTHDAY", 4, 1)
        draw_word(_line2_x, _line2_y, _name + "!", 6, 1)
    else:
        draw_word(_line1_x, _line1_y, "HAPPY", 4, 1)
        draw_word(_line2_x, _line2_y, "BIRTHDAY!", 6, 1)

    return 0.15
