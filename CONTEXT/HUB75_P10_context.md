# HUB75 P10 RGB LED Matrix Panel — Project Context

## Hardware Overview

### Panels
- 8× P10 HUB75 RGB panels, each 32×16 pixels, 1/4 scan, shift register driver
- **Arrangement: 2 columns × 4 rows** = 64×64 logical pixels
- Each panel has a HUB75 IN and OUT connector for daisy chaining
- Rows 0 and 2 (top, middle-low) mounted normally; rows 1 and 3 (middle-high, bottom) mounted 180° rotated

### Controller
- ESP32-WROOM devkit
- PlatformIO for flashing
- Library: ESP32-HUB75-MatrixPanel-DMA (mrcodetastic)

### Level Shifter
- 1× 74HCT245N (DIP): between ESP32 and Panel 1 IN, boosts 3.3V → 5V logic
- Chip power: Pin 1 (DIR)→5V, Pin 10 (GND)→GND, Pin 19 (OE)→GND, Pin 20 (VCC)→5V

### Power
- 5V high-amp supply with individual feeds to each panel; ESP32 powered separately

---

## Chain Topology — CONFIRMED

Physical layout viewed from front (logical row 0 = visual top):

```
[ chain6 / 180°rot ] [ chain7 / 180°rot ]   ← logical row 0 (visual top)
[ chain5 / normal  ] [ chain4 / normal  ]   ← logical row 1
[ chain2 / normal  ] [ chain3 / H-flip  ]   ← logical row 2
[ chain1 / H-flip  ] [ chain0 / H-flip  ]   ← logical row 3 (visual bottom)
```

Chain path: 0→1 (row3, L→R) → 2 (row2, right) → 3 (row2, R→L) → 4 (row1, right) → 5 (row1, R→L) → 6 (row0, left) → 7 (row0, L→R)

---

## GPIO Pin Mapping

### Through the 74HCT245N (ESP32 → chip → panel)

| Signal | ESP32 GPIO |
|--------|-----------|
| R1     | 25        |
| G1     | 26        |
| B1     | 27        |
| R2     | 14        |
| G2     | 12        |
| B2     | 13        |
| CLK    | 33        |
| LAT    | 32        |

### Direct ESP32 to panel (no level shifter)

| Signal | ESP32 GPIO |
|--------|-----------|
| OE     | 15        |
| A      | 23        |
| B      | 19        |
| C      | 5         |

---

## DMA Library Configuration

```cpp
HUB75_I2S_CFG mxconfig(64, 8, 8);  // physical width=64, physical height=8, 8 panels
```

Each panel is 64×8 in physical DMA space (1/4 scan: 32×16 logical = 64×8 physical). Total DMA canvas: 512×8.

---

## Scan Pattern — Confirmed Working

8-pixel block interleave with row-group swapping. Custom remap required.

```
py        = (local_y / 8) * 4 + (local_y % 4)
row_group = local_y / 4
local_px  = (local_x / 8) * 16 + (local_x % 8)      if row_group is odd
local_px  = (local_x / 8) * 16 + 8 + (local_x % 8)  if row_group is even
px        = chain_panel * 64 + local_px
```

---

## Coordinate Systems — CRITICAL

There are two coordinate systems. All content must use **visual coords** via `setVisualPixel`.

### Logical coordinates (internal remap input)
- 64×64 grid, row 0 = visual top in concept, BUT…
- **Within each 16-row panel, logical y=0 is the visual BOTTOM** (scan interleave inverts y per panel)
- Visual top of full display = logical y=15; visual bottom = logical y=48
- Never draw directly with logical coords unless you understand this inversion

### Visual coordinates (intuitive, use these for all content)
- (0,0) = top-left corner of the display as seen
- (63,0) = top-right; (0,63) = bottom-left; (63,63) = bottom-right
- Conversion formula: `logical_y = (vy/16)*16 + (15 - vy%16)`

```cpp
void setVisualPixel(int vx, int vy, uint8_t r, uint8_t g, uint8_t b) {
    if (vx<0||vx>=LOG_W||vy<0||vy>=LOG_H) return;
    int ly = (vy/PANEL_H)*PANEL_H + (PANEL_H-1 - vy%PANEL_H);
    setPixel(vx, ly, r, g, b);
}
```

**Rule: use `setVisualPixel` for all content. Use `setPixel` (logical) only for the remap itself.**

---

## Remap Function — FINAL (Phase 2 + Cyan fix)

All 8 panels confirmed correct. Diagonal stripe test passed — all stripes continuous across panel boundaries.

| Panel (log row, col) | Chain | Physical orientation | FLIPH | FLIPV |
|---|---|---|---|---|
| row0 col0 | 6 (Orange) | 180° rotated | false | true |
| row0 col1 | 7 (Purple)  | 180° rotated | false | true |
| row1 col0 | 5 (Magenta) | normal        | true  | false |
| row1 col1 | 4 (Cyan)    | normal        | true  | false |
| row2 col0 | 2 (Blue)    | normal        | false | true |
| row2 col1 | 3 (Yellow)  | normal        | false | true |
| row3 col0 | 1 (Green)   | H-flipped     | true  | false |
| row3 col1 | 0 (Red)     | H-flipped     | true  | false |

```cpp
#define LOG_W    64
#define LOG_H    64
#define PANEL_W  32
#define PANEL_H  16
#define PHYS_PPW 64
#define PHYS_H    8
#define NUM_PANELS 8

// [logical_row][logical_col], logical row 0 = visual TOP
const int  CHAIN[4][2] = { {6,7}, {5,4}, {2,3}, {1,0} };

const bool FLIPH[4][2] = {
    {false, false},  // row 0 (top)
    {true,  true},   // row 1
    {false, false},  // row 2
    {true,  true},   // row 3 (bottom)
};
const bool FLIPV[4][2] = {
    {true,  true},   // row 0 (top)
    {false, false},  // row 1
    {true,  true},   // row 2
    {false, false},  // row 3 (bottom)
};

void remap(int lx, int ly, int &px, int &py) {
    int row = ly / PANEL_H, col = lx / PANEL_W;
    int lx_ = lx % PANEL_W, ly_ = ly % PANEL_H;
    if (FLIPH[row][col]) lx_ = (PANEL_W-1) - lx_;
    if (FLIPV[row][col]) ly_ = (PANEL_H-1) - ly_;
    int cp = CHAIN[row][col];
    py = (ly_/8)*4 + (ly_%4);
    int rg = ly_/4;
    int lpx = (rg&1) ? (lx_/8)*16+(lx_%8) : (lx_/8)*16+8+(lx_%8);
    px = cp*PHYS_PPW + lpx;
}

void setPixel(int x, int y, uint8_t r, uint8_t g, uint8_t b) {
    if (x<0||x>=LOG_W||y<0||y>=LOG_H) return;
    int px, py; remap(x,y,px,py);
    dma->drawPixelRGB888(px,py,r,g,b);
}

void setVisualPixel(int vx, int vy, uint8_t r, uint8_t g, uint8_t b) {
    if (vx<0||vx>=LOG_W||vy<0||vy>=LOG_H) return;
    int ly = (vy/PANEL_H)*PANEL_H + (PANEL_H-1 - vy%PANEL_H);
    setPixel(vx, ly, r, g, b);
}
```

---

## Font Rendering

5×7 bitmap font, ASCII 32–90 (space, punctuation, digits, A–Z uppercase).

**Critical:** The font encodes each column as a byte where **bit0 = top row, bit6 = bottom row** (LSB = topmost pixel). Use `bits & (1 << ri)` — NOT `(1 << (6-ri))`. The reversed bit order was confirmed by testing: using `(6-ri)` caused every character to appear upside-down ('5' looks like '2', 'U' looks like an arch, etc.).

Always use `drawVisualChar` / `drawVisualString` with **visual coordinates**. Never call the old `drawChar` (logical coords) — it predates the visual coordinate system.

```cpp
void drawVisualChar(int cx, int cy, char c, uint8_t r, uint8_t g, uint8_t b) {
    if (c < 32 || c > 90) return;
    const uint8_t *bm = FONT[c-32];
    for (int ci = 0; ci < 5; ci++) {
        uint8_t bits = bm[ci];
        for (int ri = 0; ri < 7; ri++)
            if (bits & (1 << ri))          // bit0 = top row
                setVisualPixel(cx+ci, cy+ri, r, g, b);
    }
}

void drawVisualString(int x, int y, const char *s, uint8_t r, uint8_t g, uint8_t b) {
    while (*s) { drawVisualChar(x, y, *s++, r, g, b); x += 6; }
}
```

Character width: 5px + 1px gap = 6px per char. Height: 7px.
String pixel width: `strlen(s)*6 - 1`.

---

## Known Hardware Quirks

- A small number of individual LEDs show incorrect colour permanently — dead sub-pixels, not fixable
- A few LEDs flicker — loose bond wire internally

---

## Development Environment

- PlatformIO (VS Code extension)
- Board: esp32dev
- Framework: Arduino
- Library: `mrcodetastic/ESP32 HUB75 LED Matrix Panel DMA` (via GitHub URL in lib_deps)

---

## WiFi & OTA

ESP32 connects as a WiFi client (STA mode, never AP). Credentials in `src/credentials.h` (gitignored).

On boot the display shows the IP address in green for 3 seconds. Also printed to serial at 115200 baud.

**OTA method: ArduinoOTA** (built into ESP32 Arduino framework, no extra library).
- Hostname: `rgb-display`
- Port: 3232
- During flash: display shows "OTA UPDATING" in orange, then "OTA DONE" in green

**platformio.ini OTA config:**
```ini
upload_protocol = espota
upload_port = 192.168.0.63   ; ESP32's IP (set DHCP reservation in router so this never changes)
upload_flags =
    --port=3232
    --auth=
```

**Critical PlatformIO gotcha:** if a USB serial port is also selected in PlatformIO (e.g. COM12), it overrides `upload_port` and OTA fails with "Host COM12 Not Found". Fix: set the PlatformIO port to **Auto** (not a specific COM port) before doing an OTA upload. USB cable does not need to be unplugged.

**Workflow:**
1. First flash ever → USB (comment out espota lines, upload, then uncomment)
2. All subsequent flashes → just hit Upload with espota configured and port set to Auto

**Frame receiver:** AsyncUDP on port 5005. Accepts exactly 12,288 bytes (64×64×3 RGB888, row-major, visual top-left first). Each packet is one complete frame rendered immediately via `setVisualPixel`.

**Brightness control:** AsyncUDP on port 5006. Send a single byte (0–255). Calls `dma->setBrightness8()` directly — hardware PWM on OE pin (GPIO 15). Default on boot: 128 (50%). Server sends this whenever the brightness slider changes.

---

## Planned Architecture (next steps)

```
Phone/tablet browser
    ↕ WebSocket (input + state)
FastAPI server (Ubuntu/PC)
    ↕ UDP @ ~30fps  →  port 5005
ESP32
    → remap → DMA → panels
```

- ESP32 is dumb: receive UDP frame, render it, handle OTA. Firmware rarely changes.
- All logic (modes, games, animations) lives on the server in Python.
- Plugin system: drop a `.py` file in `modes/`, it auto-appears in the web UI.
- Web UI served by FastAPI; HA tablet embeds it as iframe.
