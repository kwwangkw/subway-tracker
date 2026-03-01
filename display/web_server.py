# SPDX-License-Identifier: MIT
# web_server.py — Tiny HTTP server for mode switching
#
# Serves a mobile-friendly page at http://display.local with mode buttons.
# No external libraries needed — raw sockets only.

import socketpool
import mdns
import wifi
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


def start(pool, port=80):
    """Start the HTTP server on the given port. Returns True if successful."""
    global _server_socket, _pool, _mdns_server
    _pool = pool

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
    """Non-blocking check for HTTP requests. Returns new mode name or None."""
    if _server_socket is None:
        return None

    try:
        client, addr = _server_socket.accept()
    except OSError:
        # No connection waiting — normal, return immediately
        return None

    new_mode = None
    try:
        client.settimeout(2)
        buf = bytearray(512)
        size = client.recv_into(buf)
        if size:
            line = buf[:size].decode("utf-8").split("\r\n")[0]
            parts = line.split(" ")
            path = parts[1] if len(parts) >= 2 else "/"

            if path.startswith("/mode/"):
                requested = path[6:].strip("/").lower()
                valid_modes = [m[0] for m in MODES]
                if requested in valid_modes:
                    new_mode = requested
                    _send_response(client, 303, "See Other",
                                   headers="Location: /\r\n")
                else:
                    _send_response(client, 404, "Not Found",
                                   body="Unknown mode")
            else:
                _send_page(client, current_mode)
    except Exception as e:
        print(f"HTTP error: {e}")
        # Send the error in the response so we can see it via curl
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

    return new_mode


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
