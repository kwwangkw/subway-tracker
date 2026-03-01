# 🚇 NYC Subway Tracker

Real-time NYC subway arrival display powered by an **Adafruit MatrixPortal S3** and two chained **64×32 HUB75 LED matrices** (128×32 total).

![Display mockup](TrainSign.ipynb)

## Hardware

| Component | Qty | Link |
|-----------|-----|------|
| Adafruit MatrixPortal S3 | 1 | [adafruit.com/5778](https://www.adafruit.com/product/5778) |
| 64×32 RGB LED Matrix (HUB75, 4mm pitch) | 2 | [adafruit.com/2278](https://www.adafruit.com/product/2278) |
| 5V 4A+ Power Supply | 1 | [adafruit.com/1466](https://www.adafruit.com/product/1466) |
| HUB75 ribbon cable | 1 | (usually included with panels) |

### Wiring

1. Plug the MatrixPortal S3 directly into the **input** HUB75 connector of the first panel
2. Chain the second panel using a ribbon cable from **output** of panel 1 → **input** of panel 2
3. Power both panels (use a Y-splitter or separate power cables — each panel draws up to 4A at full white)
4. Connect USB-C for data/programming

## Software Setup

### 1. Install CircuitPython

Download the latest CircuitPython (≥8.2.1) for the MatrixPortal S3:
- https://circuitpython.org/board/adafruit_matrixportal_s3/

Double-click the **Reset** button to enter bootloader mode (NeoPixel turns green), then drag the `.uf2` file onto the `MATRXS3BOOT` drive.

### 2. Install Required Libraries

Download the [Adafruit CircuitPython Library Bundle](https://circuitpython.org/libraries) and copy these to the `lib/` folder on your `CIRCUITPY` drive:

```
lib/
  adafruit_requests.mpy
  adafruit_connection_manager.mpy
```

### 3. Deploy Project Files

Copy these files to the **root** of your `CIRCUITPY` drive:

```
CIRCUITPY/
├── code.py              # Main entry point (runs on boot)
├── font_data.py         # Bitmap font definitions & line colors
├── mta_feed.py          # MTA GTFS-RT feed parser
├── train_sign.py        # Display rendering engine
├── settings.toml        # Wi-Fi credentials & station config
└── lib/
    ├── adafruit_requests.mpy
    └── adafruit_connection_manager.mpy
```

### 4. Configure

Edit `settings.toml` on the CIRCUITPY drive:

```toml
CIRCUITPY_WIFI_SSID     = "YourWiFiName"
CIRCUITPY_WIFI_PASSWORD = "YourWiFiPassword"

# Your station's GTFS stop ID (see below)
MTA_STOP_ID = "G22"

# Refresh interval in seconds
MTA_REFRESH_INTERVAL = "30"

# Optional: filter to specific lines (comma-separated)
# MTA_LINES_FILTER = "7,G"
```

### Finding Your Stop ID

Stop IDs can be found in the [MTA GTFS static feed](https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip) (`stops.txt`), or look them up at the [MTA developer resources](https://www.mta.info/developers).

Common examples:
| Station | Stop ID | Lines |
|---------|---------|-------|
| Court Sq | G22 | 7, G |
| Times Sq-42 St | 725 | 1,2,3,7,N,Q,R,W,S |
| Union Sq-14 St | 635 | 4,5,6,L,N,Q,R,W |
| Atlantic Ave | 617 | 2,3,4,5,B,D,N,Q,R |
| Jay St-MetroTech | A41 | A,C,F,R |

## How It Works

```
code.py (main loop)
  ├── Connects to Wi-Fi
  ├── Fetches MTA GTFS-RT protobuf feeds (no API key needed)
  │   └── mta_feed.py parses raw protobuf to extract arrivals
  ├── Renders display using bitmap fonts
  │   └── train_sign.py draws circles, text, times
  │       └── font_data.py provides 5×7 and 5×5 bitmap glyphs
  └── Refreshes every 30 seconds
```

### Display Layout (128×32)

```
┌──────────────────────────────────────────────────────┐
│ (⑦) 34 St-Hudson                             3min   │  Row 1
│──────────────────────────────────────────────────────│  Divider
│ (Ⓖ) Church Ave                               5min   │  Row 2
└──────────────────────────────────────────────────────┘
```

Each row shows:
- **Colored circle** with the line letter/number (official MTA colors)
- **Destination** name
- **Arrival time** in minutes (right-aligned)

## Holiday Banners

The `Holidays/` folder contains animated holiday banners for the same hardware. To use one, copy its `code.py` to the root of your `CIRCUITPY` drive (replacing the train sign `code.py`). No Wi-Fi required — these run entirely offline.

| Holiday | Folder | Animation |
|---------|--------|-----------|
| 🏖️ Beach Day | `Holidays/BeachDay/` | Scrolling ocean waves, sun, sand, and colorful beach umbrellas |
| 🎄 Christmas | `Holidays/Christmas/` | Falling snowflakes and Christmas trees with blinking lights |
| 🎃 Halloween | `Holidays/Halloween/` | Bobbing spiders on web threads and animated bats |
| 🇺🇸 4th of July | `Holidays/July4th/` | Red, white, and blue fireworks |
| 🎆 New Year | `Holidays/NewYear/` | Multi-color fireworks with 3-color particle trails |
| ☘️ St. Patrick's Day | `Holidays/StPatricks/` | Floating shamrocks in multiple shades of green |
| 🍂 Thanksgiving | `Holidays/Thanksgiving/` | Falling autumn leaves (maple, oak, aspen, and more) in fall colors |
| 💕 Valentine's Day | `Holidays/Valentines/` | Hearts floating upward in pinks and reds |

Each banner displays a centered holiday greeting with animated elements around the text.

## Development

The `TrainSign.ipynb` notebook is a Pillow-based mock of the LED display for prototyping the layout without hardware. Run it to preview what the display looks like.

The `TrainSign/test/` folder contains standalone test files that run on the hardware without Wi-Fi:
- `code.py` — scrolling display test with sample data
- `no_wifi_screen.py` — preview of the "No WiFi" error screen

## MTA Data

This project uses the [MTA GTFS-Realtime feeds](https://api.mta.info/) which are **free and require no API key**. Data is provided in Protocol Buffer format; the `mta_feed.py` module includes a minimal protobuf parser written in pure Python/CircuitPython.

## License

See [LICENSE](LICENSE) for details.
