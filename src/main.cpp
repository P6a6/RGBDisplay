#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>
#include <WiFi.h>
#include <AsyncUDP.h>
#include <ArduinoOTA.h>
#include "credentials.h"

// ── Display config ────────────────────────────────────────────────────────────
#define NUM_PANELS   8
#define PANEL_W     32
#define PANEL_H     16
#define LOG_W       64
#define LOG_H       64
#define PHYS_PPW    64
#define PHYS_H       8
#define FRAME_BYTES (LOG_W * LOG_H * 3)  // 12288 bytes, RGB888 row-major visual

#define UDP_PORT       5005
#define UDP_BRIGHT     5006

MatrixPanel_I2S_DMA *dma = nullptr;
AsyncUDP             udp;
AsyncUDP             udpBright;

// ── Remap ─────────────────────────────────────────────────────────────────────
const int  CHAIN[4][2] = { {6,7}, {5,4}, {2,3}, {1,0} };
const bool FLIPH[4][2] = { {false,false},{true,true},{false,false},{true,true} };
const bool FLIPV[4][2] = { {true,true},{false,false},{true,true},{false,false} };

void remap(int lx, int ly, int &px, int &py) {
    int row = ly/PANEL_H, col = lx/PANEL_W;
    int lx_ = lx%PANEL_W, ly_ = ly%PANEL_H;
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

// Visual coords: (0,0) = top-left as seen on display.
void setVisualPixel(int vx, int vy, uint8_t r, uint8_t g, uint8_t b) {
    if (vx<0||vx>=LOG_W||vy<0||vy>=LOG_H) return;
    int ly = (vy/PANEL_H)*PANEL_H + (PANEL_H-1 - vy%PANEL_H);
    setPixel(vx, ly, r, g, b);
}

// ── Render a raw 12288-byte RGB888 frame (visual row-major, top-left origin) ──
void renderFrame(const uint8_t *buf, size_t len) {
    if (len < FRAME_BYTES) return;
    for (int vy = 0; vy < LOG_H; vy++)
        for (int vx = 0; vx < LOG_W; vx++) {
            int i = (vy * LOG_W + vx) * 3;
            setVisualPixel(vx, vy, buf[i], buf[i+1], buf[i+2]);
        }
}

// ── Status screen shown on boot until first frame arrives ─────────────────────
void showStatus(const char *line1, const char *line2, uint8_t r, uint8_t g, uint8_t b) {
    dma->clearScreen();

    // 5×7 font subset (digits + A-Z + space + dot + colon)
    const uint8_t FONT[][5] = {
        {0x00,0x00,0x00,0x00,0x00}, // ' '
        {0x00,0x00,0x5F,0x00,0x00}, // '!'
        {0x00,0x07,0x00,0x07,0x00}, // '"'
        {0x14,0x7F,0x14,0x7F,0x14}, // '#'
        {0x24,0x2A,0x7F,0x2A,0x12}, // '$'
        {0x23,0x13,0x08,0x64,0x62}, // '%'
        {0x36,0x49,0x55,0x22,0x50}, // '&'
        {0x00,0x05,0x03,0x00,0x00}, // '\''
        {0x00,0x1C,0x22,0x41,0x00}, // '('
        {0x00,0x41,0x22,0x1C,0x00}, // ')'
        {0x14,0x08,0x3E,0x08,0x14}, // '*'
        {0x08,0x08,0x3E,0x08,0x08}, // '+'
        {0x00,0x50,0x30,0x00,0x00}, // ','
        {0x08,0x08,0x08,0x08,0x08}, // '-'
        {0x00,0x60,0x60,0x00,0x00}, // '.'
        {0x20,0x10,0x08,0x04,0x02}, // '/'
        {0x3E,0x51,0x49,0x45,0x3E}, // '0'
        {0x00,0x42,0x7F,0x40,0x00}, // '1'
        {0x42,0x61,0x51,0x49,0x46}, // '2'
        {0x21,0x41,0x45,0x4B,0x31}, // '3'
        {0x18,0x14,0x12,0x7F,0x10}, // '4'
        {0x27,0x45,0x45,0x45,0x39}, // '5'
        {0x3C,0x4A,0x49,0x49,0x30}, // '6'
        {0x01,0x71,0x09,0x05,0x03}, // '7'
        {0x36,0x49,0x49,0x49,0x36}, // '8'
        {0x06,0x49,0x49,0x29,0x1E}, // '9'
        {0x00,0x36,0x36,0x00,0x00}, // ':'
        {0x00,0x56,0x36,0x00,0x00}, // ';'
        {0x08,0x14,0x22,0x41,0x00}, // '<'
        {0x14,0x14,0x14,0x14,0x14}, // '='
        {0x00,0x41,0x22,0x14,0x08}, // '>'
        {0x02,0x01,0x51,0x09,0x06}, // '?'
        {0x32,0x49,0x79,0x41,0x3E}, // '@'
        {0x7E,0x11,0x11,0x11,0x7E}, // 'A'
        {0x7F,0x49,0x49,0x49,0x36}, // 'B'
        {0x3E,0x41,0x41,0x41,0x22}, // 'C'
        {0x7F,0x41,0x41,0x22,0x1C}, // 'D'
        {0x7F,0x49,0x49,0x49,0x41}, // 'E'
        {0x7F,0x09,0x09,0x09,0x01}, // 'F'
        {0x3E,0x41,0x49,0x49,0x7A}, // 'G'
        {0x7F,0x08,0x08,0x08,0x7F}, // 'H'
        {0x00,0x41,0x7F,0x41,0x00}, // 'I'
        {0x20,0x40,0x41,0x3F,0x01}, // 'J'
        {0x7F,0x08,0x14,0x22,0x41}, // 'K'
        {0x7F,0x40,0x40,0x40,0x40}, // 'L'
        {0x7F,0x02,0x0C,0x02,0x7F}, // 'M'
        {0x7F,0x04,0x08,0x10,0x7F}, // 'N'
        {0x3E,0x41,0x41,0x41,0x3E}, // 'O'
        {0x7F,0x09,0x09,0x09,0x06}, // 'P'
        {0x3E,0x41,0x51,0x21,0x5E}, // 'Q'
        {0x7F,0x09,0x19,0x29,0x46}, // 'R'
        {0x46,0x49,0x49,0x49,0x31}, // 'S'
        {0x01,0x01,0x7F,0x01,0x01}, // 'T'
        {0x3F,0x40,0x40,0x40,0x3F}, // 'U'
        {0x1F,0x20,0x40,0x20,0x1F}, // 'V'
        {0x3F,0x40,0x38,0x40,0x3F}, // 'W'
        {0x63,0x14,0x08,0x14,0x63}, // 'X'
        {0x07,0x08,0x70,0x08,0x07}, // 'Y'
        {0x61,0x51,0x49,0x45,0x43}, // 'Z'
    };

    auto drawChar = [&](int cx, int cy, char c) {
        if (c < 32 || c > 90) return;
        const uint8_t *bm = FONT[c-32];
        for (int ci = 0; ci < 5; ci++) {
            uint8_t bits = bm[ci];
            for (int ri = 0; ri < 7; ri++)
                if (bits & (1 << ri))
                    setVisualPixel(cx+ci, cy+ri, r, g, b);
        }
    };

    auto drawStr = [&](int x, int y, const char *s) {
        while (*s) { drawChar(x, y, *s++ & ~0x20); x += 6; }
    };

    drawStr(2, 22, line1);
    drawStr(2, 34, line2);
}

void setup() {
    Serial.begin(115200);

    // ── Matrix init ───────────────────────────────────────────────────────────
    HUB75_I2S_CFG mxconfig(PHYS_PPW, PHYS_H, NUM_PANELS);
    mxconfig.gpio.r1=25; mxconfig.gpio.g1=26; mxconfig.gpio.b1=27;
    mxconfig.gpio.r2=14; mxconfig.gpio.g2=12; mxconfig.gpio.b2=13;
    mxconfig.gpio.clk=33; mxconfig.gpio.lat=32; mxconfig.gpio.oe=15;
    mxconfig.gpio.a=23; mxconfig.gpio.b=19; mxconfig.gpio.c=5;
    mxconfig.driver=HUB75_I2S_CFG::SHIFTREG;
    mxconfig.clkphase=false;
    dma = new MatrixPanel_I2S_DMA(mxconfig);
    dma->begin();
    dma->setBrightness8(128);  // default 50% — server can override via UDP port 5006
    dma->clearScreen();

    showStatus("OTA TEST", "WIFI...", 0, 200, 255);

    // ── WiFi ──────────────────────────────────────────────────────────────────
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    WiFi.setAutoReconnect(true);

    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis()-t0 < 15000)
        delay(250);

    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("IP: "); Serial.println(WiFi.localIP());
        // Show IP on display for 3 seconds
        String ip = WiFi.localIP().toString();
        showStatus("READY", ip.c_str(), 0, 220, 0);
        delay(3000);
        dma->clearScreen();
    } else {
        showStatus("NO WIFI", "CHECK CREDS", 220, 0, 0);
        Serial.println("WiFi failed — check credentials.h");
    }

    // ── OTA (ArduinoOTA — PlatformIO uploads directly over WiFi) ─────────────
    ArduinoOTA.setHostname("rgb-display");
    ArduinoOTA.onStart([]() {
        dma->clearScreen();
        showStatus("OTA", "UPDATING", 255, 160, 0);
    });
    ArduinoOTA.onEnd([]() {
        showStatus("OTA", "DONE", 0, 220, 0);
    });
    ArduinoOTA.onError([](ota_error_t e) {
        showStatus("OTA", "ERROR", 220, 0, 0);
    });
    ArduinoOTA.begin();
    Serial.println("OTA hostname: rgb-display.local");

    // ── UDP frame receiver ────────────────────────────────────────────────────
    if (udp.listen(UDP_PORT)) {
        udp.onPacket([](AsyncUDPPacket pkt) {
            renderFrame(pkt.data(), pkt.length());
        });
        Serial.printf("UDP frame listener on port %d\n", UDP_PORT);
    }

    // ── UDP brightness control (single byte, 0–255) ───────────────────────────
    if (udpBright.listen(UDP_BRIGHT)) {
        udpBright.onPacket([](AsyncUDPPacket pkt) {
            if (pkt.length() >= 1)
                dma->setBrightness8(pkt.data()[0]);
        });
        Serial.printf("UDP brightness listener on port %d\n", UDP_BRIGHT);
    }
}

void loop() {
    ArduinoOTA.handle();
    delay(10);
}
