# SPDX-License-Identifier: MIT
# Created by Kevin Wang - https://github.com/kwwangkw/
# web_server.py - Tiny HTTP server for mode switching
#
# Serves a mobile-friendly page at http://display.local with mode buttons.
# No external libraries needed - raw sockets only.

import socketpool
import mdns
import wifi
import os
import gc
import time
import microcontroller

_server_socket = None
_pool = None
_mdns_server = None  # must keep a reference so it doesn't get GC'd

# Available modes - label shown on the web page
GENERAL_MODES = [
    ("train", "🚇 Subway"),
    ("clock", "🕐 Clock"),
    ("weather", "🌤️ Weather"),
    ("stocks", "📈 Stocks"),
]

HOLIDAY_MODES = [
    ("halloween", "🎃 Halloween"),
    ("christmas", "🎄 Christmas"),
    ("thanksgiving", "🦃 Thanksgiving"),
    ("july4th", "🎆 4th of July"),
    ("newyear", "🎉 New Year"),
    ("valentines", "💕 Valentine's Day"),
    ("stpatricks", "☘️ St. Patrick's"),
    ("beachday", "🏖️ Beach Day"),
    ("birthday", "🎂 Birthday"),
]

MODES = GENERAL_MODES + HOLIDAY_MODES

# Current stop configs - initialized from settings.toml, changeable via web
_stops_config = []  # list of strings like ["721:7:N", "G24:G:S"]
_pending_stops = None  # set by poll(), consumed by code.py

# Clock/weather settings - initialized from settings.toml, changeable via web
_zip_code = "10001"
_stock_symbols = "AAPL,GOOGL,MSFT"
_birthdays = ""  # Name:MM-DD,Name:MM-DD
_animated_weather = False  # animate weather icons
_wifi_ssid = ""  # Wi-Fi SSID from NVM
_wifi_pass = ""  # Wi-Fi password from NVM
_mode = "train"  # current mode, persisted via NVM


# ---------------------------------------------------------------
# NVM persistence - stores settings in microcontroller.nvm
# Format: "key1=val1\nkey2=val2\n" with a null terminator
# Keys: stops, zip, symbols, birthdays, anim, ssid, pass
# ---------------------------------------------------------------
_NVM_MARKER = b"SS"  # 2-byte marker to identify valid NVM data


def _load_nvm():
    """Load saved settings from NVM. Returns dict of key->value, or {}."""
    try:
        nvm = microcontroller.nvm
        if nvm[0:2] != _NVM_MARKER:
            return {}
        # Find null terminator
        end = 2
        while end < len(nvm) and nvm[end] != 0:
            end += 1
        raw = bytes(nvm[2:end]).decode("utf-8")
        result = {}
        for line in raw.split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                result[k] = v
        return result
    except Exception as e:
        print(f"NVM load error: {e}")
        return {}


def _save_nvm():
    """Save current settings to NVM."""
    try:
        data = (
            f"mode={_mode}\n"
            f"stops={','.join(_stops_config)}\n"
            f"zip={_zip_code}\n"
            f"symbols={_stock_symbols}\n"
            f"birthdays={_birthdays}\n"
            f"anim={1 if _animated_weather else 0}\n"
            f"ssid={_wifi_ssid}\n"
            f"pass={_wifi_pass}\n"
        )
        raw = _NVM_MARKER + data.encode("utf-8") + b"\x00"
        nvm = microcontroller.nvm
        if len(raw) > len(nvm):
            print(f"NVM save error: data too large ({len(raw)}/{len(nvm)})")
            return
        nvm[0:len(raw)] = raw
        print(f"Settings saved to NVM ({len(raw)} bytes)")
    except Exception as e:
        print(f"NVM save error: {e}")


def save_mode(mode):
    """Save the current mode to NVM."""
    global _mode
    _mode = mode
    _save_nvm()


def load_mode():
    """Load saved mode. Returns mode name from NVM, or None."""
    saved = _load_nvm()
    return saved.get("mode")


def get_wifi_creds():
    """Return (ssid, password) from NVM, or (None, None) if not set."""
    saved = _load_nvm()
    ssid = saved.get("ssid", "") or None
    pw = saved.get("pass", "") or None
    if ssid and pw:
        return ssid, pw
    return None, None


def save_wifi_creds(ssid, password):
    """Save Wi-Fi credentials to NVM."""
    global _wifi_ssid, _wifi_pass
    _wifi_ssid = ssid
    _wifi_pass = password
    _save_nvm()
    return True


def clear_wifi_creds():
    """Clear Wi-Fi credentials from NVM."""
    global _wifi_ssid, _wifi_pass
    _wifi_ssid = ""
    _wifi_pass = ""
    _save_nvm()


def start(pool, port=80):
    """Start the HTTP server on the given port. Returns True if successful."""
    global _server_socket, _pool, _mdns_server, _stops_config
    global _zip_code, _stock_symbols, _birthdays, _animated_weather
    global _wifi_ssid, _wifi_pass
    _pool = pool

    # Initialize from settings.toml (defaults)
    stops_str = os.getenv("MTA_STOPS", "")
    _stops_config[:] = [s.strip() for s in stops_str.split(",") if s.strip()]
    _zip_code = os.getenv("WEATHER_ZIP", "10001")
    _stock_symbols = os.getenv("STOCK_SYMBOLS", "AAPL,GOOGL,MSFT")
    _birthdays = os.getenv("BIRTHDAYS", "")

    # Override with NVM-saved settings (if any)
    saved = _load_nvm()
    if saved:
        print(f"NVM overrides: {list(saved.keys())}")
        if "mode" in saved and saved["mode"]:
            _mode = saved["mode"]
        if "stops" in saved and saved["stops"]:
            _stops_config[:] = [s.strip() for s in saved["stops"].split(",") if s.strip()]
        if "zip" in saved and saved["zip"]:
            _zip_code = saved["zip"]
        if "symbols" in saved and saved["symbols"]:
            _stock_symbols = saved["symbols"]
        if "birthdays" in saved:
            _birthdays = saved["birthdays"]
        if "anim" in saved:
            _animated_weather = saved["anim"] != "0"
        if "ssid" in saved and saved["ssid"]:
            _wifi_ssid = saved["ssid"]
        if "pass" in saved and saved["pass"]:
            _wifi_pass = saved["pass"]

    # Set up mDNS so http://display.local works
    try:
        _mdns_server = mdns.Server(wifi.radio)
        _mdns_server.hostname = "display"
        _mdns_server.advertise_service("_http", "_tcp", port)
        print(f"mDNS: http://display.local")
    except Exception as e:
        print(f"mDNS setup failed: {e}")

    try:
        _server_socket = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        _server_socket.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
        _server_socket.bind(("0.0.0.0", port))
        _server_socket.listen(1)
        _server_socket.setblocking(False)
        print(f"HTTP server on port {port}")
        return True
    except Exception as e:
        print(f"HTTP server failed: {e}")
        _server_socket = None
        return False


def poll(current_mode):
    """Non-blocking check for HTTP requests.

    Returns dict with optional keys:
        "mode" - new mode name to switch to
        "stops" - new list of stop config strings
        "settings" - dict with changed settings (zip)
    Returns None if no actionable request.
    """
    if _server_socket is None:
        return None

    try:
        client, addr = _server_socket.accept()
    except OSError:
        # No connection waiting - normal, return immediately
        return None

    result = None
    try:
        client.settimeout(2)
        buf = bytearray(1024)
        size = client.recv_into(buf)
        if size:
            request = buf[:size].decode("utf-8")
            line = request.split("\r\n")[0]
            parts = line.split(" ")
            method = parts[0] if parts else "GET"
            path = parts[1] if len(parts) >= 2 else "/"

            if path.startswith("/mode/"):
                requested = path[6:].strip("/").lower()
                valid_modes = [m[0] for m in MODES]
                if requested in valid_modes:
                    result = {"mode": requested}
                    _send_response(client, 303, "See Other",
                                   headers="Location: /\r\n")
                else:
                    _send_response(client, 404, "Not Found",
                                   body="Unknown mode")
            elif path == "/settings" and method == "POST":
                # Get the body - may need a second recv if headers were long
                body = ""
                if "\r\n\r\n" in request:
                    body = request.split("\r\n\r\n", 1)[1]
                if not body:
                    try:
                        buf2 = bytearray(256)
                        s2 = client.recv_into(buf2)
                        if s2:
                            body = buf2[:s2].decode("utf-8")
                    except Exception:
                        pass
                settings = _parse_settings_form(body)
                if settings:
                    result = {"settings": settings}
                _send_response(client, 303, "See Other",
                               headers="Location: /\r\n")
            elif path == "/reset-wifi" and method == "POST":
                clear_wifi_creds()
                _send_response(client, 200, "OK",
                               body="Wi-Fi reset. Rebooting...")
                try:
                    client.close()
                except Exception:
                    pass
                time.sleep(1)
                microcontroller.reset()
            else:
                _send_page(client, current_mode)
    except Exception as e:
        print(f"HTTP error: {e}")
        try:
            err = str(e)
            client.send(f"HTTP/1.1 500 Error\r\nContent-Length: {len(err)}\r\nConnection: close\r\n\r\n{err}".encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            client.close()
        except Exception:
            pass

    return result


def _parse_settings_form(body):
    """Parse URL-encoded form body for all settings.

    Returns dict with changed values, or None.
    """
    global _zip_code, _stock_symbols, _birthdays, _animated_weather
    fields = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            # URL-decode: + -> space, %XX -> char
            v = v.replace("+", " ")
            i = 0
            decoded = []
            while i < len(v):
                if v[i] == "%" and i + 2 < len(v):
                    try:
                        decoded.append(chr(int(v[i+1:i+3], 16)))
                        i += 3
                        continue
                    except ValueError:
                        pass
                decoded.append(v[i])
                i += 1
            fields[k] = "".join(decoded).strip()

    changed = {}

    # Stops
    if "stops" in fields:
        raw = fields["stops"].upper()
        new_stops = []
        for entry in raw.split(","):
            entry = entry.strip()
            if entry and entry.split(":")[0]:
                new_stops.append(entry)
        if new_stops and new_stops != _stops_config:
            _stops_config[:] = new_stops
            changed["stops"] = list(new_stops)
            print(f"Stops updated: {new_stops}")

    # Zip code
    if "zip" in fields and fields["zip"]:
        new_zip = fields["zip"]
        if new_zip != _zip_code:
            _zip_code = new_zip
            changed["zip"] = new_zip

    # Stock symbols
    if "symbols" in fields and fields["symbols"]:
        new_sym = fields["symbols"].upper().replace(" ", "")
        if new_sym != _stock_symbols:
            _stock_symbols = new_sym
            changed["symbols"] = new_sym

    # Birthdays
    if "birthdays" in fields:
        new_bd = fields["birthdays"].strip()
        if new_bd != _birthdays:
            _birthdays = new_bd
            changed["birthdays"] = new_bd

    # Animated weather (checkbox: present=on, absent=off)
    new_anim = "anim" in fields
    if new_anim != _animated_weather:
        _animated_weather = new_anim
        changed["animated"] = new_anim

    if changed:
        print(f"Settings updated: {changed}")
        _save_nvm()
        return changed
    return None


def _send_response(client, code, reason, body="", headers="",
                   content_type="text/html; charset=utf-8"):
    """Send a minimal HTTP response."""
    header = (
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"{headers}"
        f"\r\n"
    )
    client.send(header.encode("utf-8"))
    if body:
        client.send(body.encode("utf-8"))


def _send_chunked(client, code, reason,
                  content_type="text/html; charset=utf-8"):
    """Send HTTP header for chunked transfer. Call _chunk()/_end_chunks()."""
    header = (
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Transfer-Encoding: chunked\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    client.send(header.encode("utf-8"))


def _chunk(client, text):
    """Send one chunk of a chunked response."""
    data = text.encode("utf-8")
    client.send(f"{len(data):x}\r\n".encode("utf-8"))
    client.send(data)
    client.send(b"\r\n")


def _end_chunks(client):
    """Send the final empty chunk."""
    client.send(b"0\r\n\r\n")


_CSS = (
    "<style>"
    "*{margin:0;padding:0;box-sizing:border-box}"
    "body{font-family:sans-serif;background:#111;color:#fff;"
    "padding:20px;max-width:400px;margin:0 auto}"
    "h1{text-align:center;margin-bottom:8px}"
    ".s{text-align:center;color:#666;font-size:.8em;margin-bottom:20px}"
    ".b{display:block;padding:14px 20px;margin:8px 0;background:#222;"
    "color:#fff;text-decoration:none;border-radius:10px;font-size:1.1em;"
    "text-align:center;border:1px solid #333}"
    ".b.a{background:#1a3a1a;border-color:#2d5a2d;color:#6f6}"
    ".row{margin:8px 0}"
    ".row label{display:block;color:#888;font-size:.8em;margin-bottom:4px}"
    ".row input{width:100%;padding:10px 12px;background:#222;color:#fff;"
    "border:1px solid #333;border-radius:8px;font-size:1em;"
    "font-family:monospace}"
    ".row input:focus{border-color:#555;outline:none}"
    ".hint{color:#555;font-size:.75em;margin-top:4px}"
    ".sb{display:block;width:100%;padding:14px;margin:12px 0;background:#1a2a4a;"
    "color:#8af;border:1px solid #2a4a7a;border-radius:10px;font-size:1em;"
    "cursor:pointer}"
    ".sb:active{background:#2a3a5a}"
    "details{margin-top:16px;border-top:1px solid #333;padding-top:12px}"
    "summary{color:#aaa;font-size:1em;cursor:pointer;padding:8px 0;"
    "list-style:none;display:flex;align-items:center;gap:6px}"
    "summary::-webkit-details-marker{display:none}"
    "summary::before{content:'\\25b6';font-size:.7em;transition:transform .2s}"
    "details[open] summary::before{transform:rotate(90deg)}"
    "details .inner{padding-top:8px}"
    ".tabs{margin-top:12px}"
    ".tabs input[type=radio]{display:none}"
    ".tabs label{display:inline-block;padding:10px 20px;background:#222;"
    "color:#888;border:1px solid #333;border-radius:10px 10px 0 0;"
    "cursor:pointer;font-size:1em;margin-right:4px}"
    ".tabs input[type=radio]:checked+label{background:#1a3a1a;color:#6f6;"
    "border-color:#2d5a2d}"
    ".tp{display:none;padding-top:4px}"
    "#t1:checked~#p1{display:block}"
    "#t2:checked~#p2{display:block}"
    "</style>"
)

_LABELS = {
    "train": "Subway",
    "clock": "Clock",
    "weather": "Weather",
    "stocks": "Stocks",
    "halloween": "Halloween",
    "christmas": "Christmas",
    "thanksgiving": "Thanksgiving",
    "july4th": "4th of July",
    "newyear": "New Year",
    "valentines": "Valentines",
    "stpatricks": "St Patricks",
    "beachday": "Beach Day",
    "birthday": "Birthday",
}


def _send_page(client, current_mode):
    """Send the mode-selection HTML page."""
    ip = str(wifi.radio.ipv4_address)

    # Build page in small pieces, join at end
    parts = []
    parts.append(
        "<!DOCTYPE html><html><head>"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Display</title>"
    )
    parts.append(_CSS)
    parts.append("</head><body><h1>Display Control</h1>")
    parts.append('<div class="s">')
    parts.append(ip)
    parts.append("</div>")

    # --- Mode buttons ---
    _is_holiday = any(m[0] == current_mode for m in HOLIDAY_MODES)
    parts.append('<div class="tabs">')
    if _is_holiday:
        parts.append('<input type="radio" id="t1" name="tab">')
        parts.append('<label for="t1">General</label>')
        parts.append('<input type="radio" id="t2" name="tab" checked>')
    else:
        parts.append('<input type="radio" id="t1" name="tab" checked>')
        parts.append('<label for="t1">General</label>')
        parts.append('<input type="radio" id="t2" name="tab">')
    parts.append('<label for="t2">Holidays</label>')
    parts.append('<div class="tp" id="p1">')

    for mode_id, _emoji_label in GENERAL_MODES:
        lbl = _LABELS.get(mode_id, mode_id)
        if mode_id == current_mode:
            parts.append('<a class="b a" href="#">')
            parts.append(lbl)
            parts.append(" [ON]</a>")
        else:
            parts.append('<a class="b" href="/mode/')
            parts.append(mode_id)
            parts.append('">')
            parts.append(lbl)
            parts.append("</a>")

    parts.append('</div><div class="tp" id="p2">')

    for mode_id, _emoji_label in HOLIDAY_MODES:
        lbl = _LABELS.get(mode_id, mode_id)
        if mode_id == current_mode:
            parts.append('<a class="b a" href="#">')
            parts.append(lbl)
            parts.append(" [ON]</a>")
        else:
            parts.append('<a class="b" href="/mode/')
            parts.append(mode_id)
            parts.append('">')
            parts.append(lbl)
            parts.append("</a>")

    parts.append('</div></div>')

    # --- Collapsible settings ---
    parts.append("<details>")
    parts.append("<summary>Settings</summary>")
    parts.append('<div class="inner">')
    parts.append('<form method="POST" action="/settings">')

    # Stations
    stops_val = ",".join(_stops_config)
    parts.append('<div class="row"><label>Train Stops</label>')
    parts.append('<input name="stops" value="')
    parts.append(stops_val)
    parts.append('" placeholder="721:7:N,G24:G:S"></div>')
    parts.append('<div class="hint">STOP:LINE:DIR comma-separated</div>')

    # Zip code
    parts.append('<div class="row"><label>Zip Code</label>')
    parts.append('<input name="zip" value="')
    parts.append(_zip_code)
    parts.append('" placeholder="10001"></div>')
    parts.append('<div class="hint">Weather location &amp; clock timezone</div>')

    # Stock symbols
    parts.append('<div class="row"><label>Stock Symbols</label>')
    parts.append('<input name="symbols" value="')
    parts.append(_stock_symbols)
    parts.append('" placeholder="AAPL,GOOGL,MSFT"></div>')
    parts.append('<div class="hint">Comma-separated ticker symbols</div>')

    # Birthdays
    parts.append('<div class="row"><label>Birthdays</label>')
    parts.append('<input name="birthdays" value="')
    parts.append(_birthdays)
    parts.append('" placeholder="Alice:3-14,Bob:7-22"></div>')
    parts.append('<div class="hint">Name:MM-DD comma-separated</div>')

    # Animated weather toggle
    parts.append('<div class="row" style="margin-top:12px;display:flex;'
                 'align-items:center;justify-content:space-between">')
    parts.append('<span style="color:#888;font-size:.8em">Animated Weather Icons</span>')
    parts.append('<label style="position:relative;display:inline-block;width:44px;height:24px">')
    parts.append('<input type="checkbox" name="anim" value="1" style="opacity:0;width:0;height:0"')
    if _animated_weather:
        parts.append(' checked')
    parts.append('>')
    parts.append('<span style="position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;'
                 'background:#333;border-radius:24px;transition:.3s"></span>')
    parts.append('<span style="position:absolute;height:18px;width:18px;left:3px;bottom:3px;'
                 'background:#888;border-radius:50%;transition:.3s;pointer-events:none"></span>')
    parts.append('</label></div>')
    parts.append('<style>.row input:checked+span{background:#2d5a2d}'
                 '.row input:checked+span+span{transform:translateX(20px);background:#6f6}</style>')

    parts.append('<button type="submit" class="sb">Save</button>')
    parts.append("</form>")

    # Reset Wi-Fi (separate form so it doesn't interfere with settings save)
    parts.append('<form method="POST" action="/reset-wifi" '
                 'onsubmit="return confirm(\'Reset Wi-Fi? The display will reboot into setup mode.\')">')
    parts.append('<button type="submit" style="display:block;width:100%;padding:14px;'
                 'margin:8px 0;background:#3a1a1a;color:#f66;border:1px solid #5a2d2d;'
                 'border-radius:10px;font-size:1em;cursor:pointer">Reset Wi-Fi</button>')
    parts.append("</form>")
    parts.append("</div>")
    parts.append("</details>")

    parts.append("</body></html>")
    body = "".join(parts)
    _send_response(client, 200, "OK", body=body)
