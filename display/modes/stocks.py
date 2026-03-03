# modes/stocks.py - Stock Ticker display mode
#
# Shows stock quotes cycling through configured symbols.
# Uses Yahoo Finance chart API (free, no key, no rate limit).
# Configure STOCK_SYMBOLS in settings.toml.

import time
import os
import gc
import ssl
import adafruit_requests

from train_sign import _dim, COLOR_BLACK, COLOR_WHITE

WIDTH = 128
HEIGHT = 32

# Configuration
SYMBOLS = os.getenv("STOCK_SYMBOLS", "AAPL,GOOGL,MSFT")
REFRESH_INTERVAL = 300  # 5 minutes
CYCLE_INTERVAL = 15      # seconds between symbol switches

_bitmap = None
_palette = None
_requests = None

_last_fetch = 0
_needs_redraw = True
_symbol_list = []        # list of ticker strings
_quotes = {}             # symbol -> {price, change, pct}
_current_idx = 0         # which symbol is currently displayed
_last_cycle = 0          # time of last symbol switch
_fetch_error = False


def _set_pixel(x, y, c):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        _bitmap[x, y] = c


def _draw_small_text(x, y, text, color):
    """Draw text using the 5x7 font."""
    from font_data import FONT_5x7
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            x += 4
            continue
        w = len(glyph)
        for col_i in range(w):
            col_byte = glyph[col_i]
            for row_i in range(7):
                if col_byte & (1 << row_i):
                    _set_pixel(x + col_i, y + row_i, color)
        x += w + 1
    return x


def _measure_text(text):
    """Measure text width in pixels."""
    from font_data import FONT_5x7
    w = 0
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph:
            w += len(glyph) + 1
    return w - 1 if w > 0 else 0


def _draw_large_text(x, y, text, color):
    """Draw text using the 5x7 font at 2x scale (10x14)."""
    from font_data import FONT_5x7
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph is None:
            x += 8
            continue
        w = len(glyph)
        for col_i in range(w):
            col_byte = glyph[col_i]
            for row_i in range(7):
                if col_byte & (1 << row_i):
                    _set_pixel(x + col_i * 2, y + row_i * 2, color)
                    _set_pixel(x + col_i * 2 + 1, y + row_i * 2, color)
                    _set_pixel(x + col_i * 2, y + row_i * 2 + 1, color)
                    _set_pixel(x + col_i * 2 + 1, y + row_i * 2 + 1, color)
        x += w * 2 + 2
    return x


def _measure_large_text(text):
    """Measure text width at 2x scale."""
    from font_data import FONT_5x7
    w = 0
    for ch in text:
        glyph = FONT_5x7.get(ch, FONT_5x7.get(" "))
        if glyph:
            w += len(glyph) * 2 + 2
    return w - 2 if w > 0 else 0


def _draw_triangle_up(x, y, color):
    """Draw a small up triangle (5 wide, 4 tall)."""
    _set_pixel(x + 2, y, color)
    _set_pixel(x + 1, y + 1, color)
    _set_pixel(x + 2, y + 1, color)
    _set_pixel(x + 3, y + 1, color)
    for i in range(5):
        _set_pixel(x + i, y + 2, color)
    for i in range(5):
        _set_pixel(x + i, y + 3, color)


def _draw_triangle_down(x, y, color):
    """Draw a small down triangle (5 wide, 4 tall)."""
    for i in range(5):
        _set_pixel(x + i, y, color)
    for i in range(5):
        _set_pixel(x + i, y + 1, color)
    _set_pixel(x + 1, y + 2, color)
    _set_pixel(x + 2, y + 2, color)
    _set_pixel(x + 3, y + 2, color)
    _set_pixel(x + 2, y + 3, color)


def _fetch_quotes(requests_session):
    """Fetch quotes for all symbols from Yahoo Finance."""
    global _quotes, _fetch_error

    for sym in _symbol_list:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            f"?range=1d&interval=1d"
        )
        try:
            resp = requests_session.get(url)
            data = resp.json()
            resp.close()

            result = data.get("chart", {}).get("result")
            if result and len(result) > 0:
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice", 0)
                prev = meta.get("chartPreviousClose", 0)
                change = price - prev if prev else 0
                pct = (change / prev * 100) if prev else 0

                _quotes[sym] = {
                    "price": price,
                    "change": change,
                    "pct": pct,
                }
                print(f"Stock {sym}: ${price:.2f} ({change:+.2f}, {pct:+.2f}%)")
            else:
                err = data.get("chart", {}).get("error")
                if err:
                    print(f"Stock API error ({sym}): {err}")
        except Exception as e:
            print(f"Stock fetch error ({sym}): {e}")
            _fetch_error = True

        gc.collect()

    if _quotes:
        _fetch_error = False


def update_config(symbols=None, **kwargs):
    """Update stock config."""
    global SYMBOLS, _symbol_list, _last_fetch, _quotes, _current_idx
    if symbols is not None and symbols != SYMBOLS:
        SYMBOLS = symbols
        _symbol_list = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]
        _quotes = {}
        _current_idx = 0
        _last_fetch = 0
    print(f"Stock config updated: symbols={SYMBOLS}")


def setup(bitmap, palette, pool=None, **kwargs):
    """Initialize stock ticker mode."""
    global _bitmap, _palette, _requests, _last_fetch
    global _quotes, _current_idx, _last_cycle, _fetch_error, _needs_redraw
    global _symbol_list

    _bitmap = bitmap
    _palette = palette
    _last_fetch = 0
    _quotes = {}
    _current_idx = 0
    _last_cycle = 0
    _fetch_error = False
    _needs_redraw = True
    _symbol_list = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]

    # Set up colors
    palette[COLOR_BLACK] = 0x000000
    wr, wg, wb = _dim(0xFF, 0xFF, 0xFF)
    palette[COLOR_WHITE] = (wr << 16) | (wg << 8) | wb

    # Ticker symbol color (bright white)
    palette[2] = palette[COLOR_WHITE]

    # Price color (warm yellow)
    pr, pg, pb = _dim(0xFF, 0xDD, 0x44)
    palette[3] = (pr << 16) | (pg << 8) | pb

    # Green (positive change)
    gr, gg, gb = _dim(0x00, 0xFF, 0x44)
    palette[4] = (gr << 16) | (gg << 8) | gb

    # Red (negative change)
    rr, rg, rb = _dim(0xFF, 0x22, 0x22)
    palette[5] = (rr << 16) | (rg << 8) | rb

    # Dim text (neutral/labels)
    dr, dg, db = _dim(0x88, 0x88, 0x88)
    palette[6] = (dr << 16) | (dg << 8) | db

    # Separator line color
    sr, sg, sb = _dim(0x33, 0x33, 0x33)
    palette[7] = (sr << 16) | (sg << 8) | sb

    # Clear display
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    # Set up HTTP session
    if pool is not None:
        ssl_context = ssl.create_default_context()
        _requests = adafruit_requests.Session(pool, ssl_context)

    print(f"Stock mode: symbols={SYMBOLS}")


def animate(bitmap):
    """Update stock display. Returns sleep time."""
    global _last_fetch, _needs_redraw, _current_idx, _last_cycle

    now = time.monotonic()

    # Fetch quotes periodically
    if _requests is not None and (now - _last_fetch >= REFRESH_INTERVAL or not _quotes):
        _last_fetch = now
        _fetch_quotes(_requests)
        _needs_redraw = True

    # Cycle through symbols
    if len(_symbol_list) > 1 and now - _last_cycle >= CYCLE_INTERVAL:
        _last_cycle = now
        _current_idx = (_current_idx + 1) % len(_symbol_list)
        _needs_redraw = True

    # Only redraw when needed
    if not _needs_redraw:
        return 0.5
    _needs_redraw = False

    # Clear
    for y in range(HEIGHT):
        for x in range(WIDTH):
            bitmap[x, y] = 0

    if not _quotes:
        # Loading state
        _draw_small_text(30, 12, "LOADING...", COLOR_WHITE)
        return 0.5

    sym = _symbol_list[_current_idx % len(_symbol_list)]
    quote = _quotes.get(sym)

    if quote is None:
        _draw_small_text(10, 12, f"NO DATA: {sym}", COLOR_WHITE)
        return 1.0

    price = quote["price"]
    change = quote["change"]
    pct = quote["pct"]

    # Determine color based on change
    if change > 0:
        change_color = 4   # green
    elif change < 0:
        change_color = 5   # red
    else:
        change_color = 6   # gray/neutral

    # --- Row 1: Ticker symbol (top left) ---
    _draw_small_text(2, 2, sym, 2)

    # --- Separator line ---
    for x in range(WIDTH):
        _set_pixel(x, 10, 7)

    # --- Row 2: Price (large) ---
    # Format price
    if price >= 1000:
        price_str = f"{int(round(price))}"
    elif price >= 100:
        price_str = f"{price:.1f}"
    else:
        price_str = f"{price:.2f}"

    price_x = 2
    _draw_large_text(price_x, 13, price_str, 3)

    # --- Right side: Change + percent (right-aligned, vertically centered) ---
    # Bottom zone: y=11..31 (21px). Two lines of 7px + 2px gap = 16px.
    # Centered: top = 11 + (21-16)//2 = 13. Lines at y=13 and y=22.
    line1_y = 13
    line2_y = 22

    # Format strings
    change_str = f"${abs(change):.2f}"
    if abs(change) >= 100:
        change_str = f"${abs(change):.1f}"

    pct_str = f"{abs(pct):.2f}%"
    if abs(pct) >= 10:
        pct_str = f"{abs(pct):.1f}%"

    # Right-align both lines to the display edge
    change_w = _measure_text(change_str)
    pct_w = _measure_text(pct_str)
    change_x = WIDTH - change_w - 2
    pct_x = WIDTH - pct_w - 2

    # Arrow indicator - left of the wider text block, vertically centered
    wider_x = min(change_x, pct_x)
    arrow_x = wider_x - 8
    arrow_y = line1_y + 5  # centered between the two text lines
    if change > 0:
        _draw_triangle_up(arrow_x, arrow_y, change_color)
    elif change < 0:
        _draw_triangle_down(arrow_x, arrow_y, change_color)

    _draw_small_text(change_x, line1_y, change_str, change_color)
    _draw_small_text(pct_x, line2_y, pct_str, change_color)

    return 0.5
