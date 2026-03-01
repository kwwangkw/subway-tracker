# SPDX-License-Identifier: MIT
# web_server.py — Tiny HTTP server for mode switching
#
# Serves a mobile-friendly page at http://display.local with mode buttons.
# No external libraries needed — raw sockets only.

import socketpool
import mdns
import wifi
import os
import gc

_server_socket = None
_pool = None
_mdns_server = None  # must keep a reference so it doesn't get GC'd

# Available modes — label shown on the web page
MODES = [
    ("train", "🚇 Train Sign"),
    ("halloween", "🎃 Halloween"),
    ("christmas", "🎄 Christmas"),
    ("thanksgiving", "🦃 Thanksgiving"),
    ("july4th", "🎆 4th of July"),
    ("newyear", "🎉 New Year"),
    ("valentines", "💕 Valentine's Day"),
    ("stpatricks", "☘️ St. Patrick's"),
    ("beachday", "🏖️ Beach Day"),
]

# Current stop configs — initialized from settings.toml, changeable via web
_stops_config = []  # list of strings like ["721:7:N", "G24:G:S"]
_pending_stops = None  # set by poll(), consumed by code.py


def start(pool, port=80):
    """Start the HTTP server on the given port. Returns True if successful."""
    global _server_socket, _pool, _mdns_server, _stops_config
    _pool = pool

    # Initialize stops from settings.toml
    stops_str = os.getenv("MTA_STOPS", "")
    _stops_config[:] = [s.strip() for s in stops_str.split(",") if s.strip()]

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
        "mode" — new mode name to switch to
        "stops" — new list of stop config strings
    Returns None if no actionable request.
    """
    if _server_socket is None:
        return None

    try:
        client, addr = _server_socket.accept()
    except OSError:
        # No connection waiting — normal, return immediately
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
            elif path == "/stops" and method == "POST":
                # Get the body — may need a second recv if headers were long
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
                new_stops = _parse_stops_form(body)
                if new_stops:
                    _stops_config[:] = new_stops
                    result = {"stops": list(new_stops)}
                    print(f"Stops updated: {new_stops}")
                _send_response(client, 303, "See Other",
                               headers="Location: /\r\n")
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


def _parse_stops_form(body):
    """Parse URL-encoded form body for the stops field.

    Returns list of non-empty stop config strings, or None if invalid.
    """
    # Extract the stops= value from the form body
    raw = ""
    for pair in body.split("&"):
        if pair.startswith("stops="):
            raw = pair[6:]
            break

    # URL-decode: + → space, %XX → char
    raw = raw.replace("+", " ")
    i = 0
    decoded = []
    while i < len(raw):
        if raw[i] == "%" and i + 2 < len(raw):
            try:
                decoded.append(chr(int(raw[i+1:i+3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        decoded.append(raw[i])
        i += 1
    raw = "".join(decoded).strip().upper()

    # Split on commas, validate each entry has at least a stop ID
    new_stops = []
    for entry in raw.split(","):
        entry = entry.strip()
        if entry and entry.split(":")[0]:
            new_stops.append(entry)

    return new_stops if new_stops else None


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
    "h2{margin:24px 0 12px;font-size:1em;color:#aaa;border-top:1px solid #333;"
    "padding-top:16px}"
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
    "</style>"
)

_LABELS = {
    "train": "Train Sign",
    "halloween": "Halloween",
    "christmas": "Christmas",
    "thanksgiving": "Thanksgiving",
    "july4th": "4th of July",
    "newyear": "New Year",
    "valentines": "Valentines",
    "stpatricks": "St Patricks",
    "beachday": "Beach Day",
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

    # --- Station config form ---
    parts.append("<h2>Stations</h2>")
    parts.append('<form method="POST" action="/stops">')
    stops_val = ",".join(_stops_config)
    parts.append('<div class="row"><label>Stops</label>')
    parts.append('<input name="stops" value="')
    parts.append(stops_val)
    parts.append('" placeholder="721:7:N,G24:G:S"></div>')
    parts.append('<div class="hint">STOP:LINE:DIR comma-separated — nearest 2 arrivals shown</div>')
    parts.append('<button type="submit" class="sb">Update Stations</button>')
    parts.append("</form>")

    # --- Mode buttons ---
    parts.append("<h2>Mode</h2>")

    for mode_id, _emoji_label in MODES:
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

    parts.append("</body></html>")
    body = "".join(parts)
    _send_response(client, 200, "OK", body=body)
