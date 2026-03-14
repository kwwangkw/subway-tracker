# Created by Kevin Wang - https://github.com/kwwangkw/
# wifi_setup.py - Wi-Fi provisioning via AP hotspot
#
# When no Wi-Fi credentials are available, this module:
# 1. Starts an AP hotspot named "Display-Setup"
# 2. Serves a captive portal at 192.168.4.1 with a form to enter SSID/password
# 3. Saves credentials to NVM and reboots

import wifi
import socketpool
import time
import microcontroller

AP_SSID = "Display-Setup"
AP_IP = "192.168.4.1"
AP_PORT = 80

_CSS = (
    "<style>"
    "*{margin:0;padding:0;box-sizing:border-box}"
    "body{font-family:sans-serif;background:#111;color:#fff;"
    "padding:20px;max-width:400px;margin:0 auto}"
    "h1{text-align:center;margin-bottom:8px}"
    ".s{text-align:center;color:#888;font-size:.85em;margin-bottom:20px}"
    ".row{margin:12px 0}"
    ".row label{display:block;color:#888;font-size:.8em;margin-bottom:4px}"
    ".row input{width:100%;padding:12px;background:#222;color:#fff;"
    "border:1px solid #333;border-radius:8px;font-size:1em}"
    ".row input:focus{border-color:#555;outline:none}"
    ".sb{display:block;width:100%;padding:14px;margin:16px 0;background:#1a3a1a;"
    "color:#6f6;border:1px solid #2d5a2d;border-radius:10px;font-size:1em;"
    "cursor:pointer}"
    ".sb:active{background:#2a4a2a}"
    ".ok{text-align:center;color:#6f6;font-size:1.1em;margin-top:30px}"
    "</style>"
)


def _send_response(client, code, reason, body=""):
    """Send a minimal HTTP response."""
    header = (
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    client.send(header.encode("utf-8"))
    if body:
        client.send(body.encode("utf-8"))


def _build_setup_page():
    """Build the Wi-Fi setup HTML page."""
    return (
        "<!DOCTYPE html><html><head>"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Display Setup</title>"
        + _CSS +
        "</head><body>"
        "<h1>Display Setup</h1>"
        '<div class="s">Enter your Wi-Fi network details</div>'
        '<form method="POST" action="/save">'
        '<div class="row"><label>Wi-Fi Network Name</label>'
        '<input name="ssid" placeholder="Your Wi-Fi name" required></div>'
        '<div class="row"><label>Wi-Fi Password</label>'
        '<input name="pass" type="password" placeholder="Your Wi-Fi password" required></div>'
        '<button type="submit" class="sb">Connect</button>'
        "</form>"
        "</body></html>"
    )


def _build_success_page():
    """Build the success page shown after saving credentials."""
    return (
        "<!DOCTYPE html><html><head>"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Display Setup</title>"
        + _CSS +
        "</head><body>"
        "<h1>Display Setup</h1>"
        '<div class="ok">Wi-Fi saved! Rebooting...</div>'
        '<div class="s" style="margin-top:12px">'
        "The display will connect to your Wi-Fi network shortly.<br>"
        "You can close this page.</div>"
        "</body></html>"
    )


def _url_decode(s):
    """Decode URL-encoded string (+ -> space, %XX -> char)."""
    s = s.replace("+", " ")
    i = 0
    decoded = []
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                decoded.append(chr(int(s[i+1:i+3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        decoded.append(s[i])
        i += 1
    return "".join(decoded)


def _parse_form(body):
    """Parse URL-encoded form body. Returns dict."""
    fields = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            fields[k] = _url_decode(v)
    return fields


def run(bitmap, palette, wdt=None):
    """Start AP mode and serve the setup portal.

    This function blocks until credentials are saved, then reboots.
    bitmap/palette are used to draw status on the LED matrix.

    Args:
        bitmap: display bitmap for drawing status
        palette: display palette
        wdt: watchdog timer to feed (or None)
    """
    import web_server

    # Draw setup instructions on the matrix
    from train_sign import draw_wifi_setup_screen
    draw_wifi_setup_screen(bitmap, palette)

    # Start AP
    print(f"Starting AP: {AP_SSID}")
    wifi.radio.stop_station()
    wifi.radio.start_ap(AP_SSID)
    print(f"AP started. IP: {wifi.radio.ipv4_address_ap}")

    # Start server
    pool = socketpool.SocketPool(wifi.radio)
    server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", AP_PORT))
    server.listen(1)
    server.setblocking(False)
    print(f"Setup server on port {AP_PORT}")

    # Serve until credentials saved
    while True:
        if wdt:
            wdt.feed()

        try:
            client, addr = server.accept()
        except OSError:
            time.sleep(0.1)
            continue

        try:
            client.settimeout(3)
            buf = bytearray(1024)
            size = client.recv_into(buf)
            if not size:
                client.close()
                continue

            request = buf[:size].decode("utf-8")
            line = request.split("\r\n")[0]
            parts = line.split(" ")
            method = parts[0] if parts else "GET"
            path = parts[1] if len(parts) >= 2 else "/"

            if path == "/save" and method == "POST":
                # Parse form body
                body = ""
                if "\r\n\r\n" in request:
                    body = request.split("\r\n\r\n", 1)[1]
                if not body:
                    try:
                        buf2 = bytearray(512)
                        s2 = client.recv_into(buf2)
                        if s2:
                            body = buf2[:s2].decode("utf-8")
                    except Exception:
                        pass

                fields = _parse_form(body)
                ssid = fields.get("ssid", "").strip()
                password = fields.get("pass", "").strip()

                if ssid and password:
                    # Save to NVM
                    web_server.save_wifi_creds(ssid, password)
                    _send_response(client, 200, "OK",
                                   body=_build_success_page())
                    client.close()
                    time.sleep(2)
                    # Reboot to connect with new creds
                    print("Rebooting with new Wi-Fi creds...")
                    microcontroller.reset()
                else:
                    _send_response(client, 200, "OK",
                                   body=_build_setup_page())
            elif path == "/generate_204" or path == "/gen_204":
                # Android captive portal detection -> redirect
                _send_response(client, 302, "Found", body="",)
                # Send location header manually
            elif path == "/hotspot-detect.html":
                # Apple captive portal detection -> serve page
                _send_response(client, 200, "OK",
                               body=_build_setup_page())
            else:
                _send_response(client, 200, "OK",
                               body=_build_setup_page())
        except Exception as e:
            print(f"Setup server error: {e}")
        finally:
            try:
                client.close()
            except Exception:
                pass
