/**
 * HUB75 4-Panel Chain Test — Anti-Noise Edition
 *
 * 4× P10 32×16 daisy-chained.
 * Map 1 remap, slow clock, max blanking, reduced brightness.
 */

#include <Arduino.h>
#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>

MatrixPanel_I2S_DMA *dma = nullptr;

#define PANELS      4
#define PANEL_W     32
#define PANEL_H     16
#define PHYS_PPW    64
#define PHYS_PPH    8
#define LOG_W       (PANEL_W * PANELS)
#define LOG_H       PANEL_H
#define PHYS_W      (PHYS_PPW * PANELS)
#define PHYS_H      PHYS_PPH

void remap(int lx, int ly, int &px, int &py) {
    int panel = lx / PANEL_W;
    int local_x = lx % PANEL_W;
    py = (ly / 8) * 4 + (ly % 4);
    int row_group = ly / 4;
    int local_px;
    if (row_group & 1)
        local_px = (local_x / 8) * 16 + (local_x % 8);
    else
        local_px = (local_x / 8) * 16 + 8 + (local_x % 8);
    px = panel * PHYS_PPW + local_px;
}

void setPixel(int x, int y, uint16_t col) {
    if (x < 0 || x >= LOG_W || y < 0 || y >= LOG_H) return;
    int px, py;
    remap(x, y, px, py);
    if (px >= 0 && px < PHYS_W && py >= 0 && py < PHYS_H)
        dma->drawPixel(px, py, col);
}

void clearAll() { dma->clearScreen(); }

void fillRect(int x, int y, int w, int h, uint16_t col) {
    for (int j = y; j < y + h; j++)
        for (int i = x; i < x + w; i++)
            setPixel(i, j, col);
}

void drawRect(int x, int y, int w, int h, uint16_t col) {
    for (int i = x; i < x + w; i++) { setPixel(i, y, col); setPixel(i, y + h - 1, col); }
    for (int j = y; j < y + h; j++) { setPixel(x, j, col); setPixel(x + w - 1, j, col); }
}

const uint8_t digits[][5] = {
    {0x00,0x42,0x7F,0x40,0x00},
    {0x62,0x51,0x49,0x49,0x46},
    {0x22,0x49,0x49,0x49,0x36},
    {0x18,0x14,0x12,0x7F,0x10},
};

void drawDigit(int x, int y, int d, uint16_t col) {
    if (d < 1 || d > 4) return;
    const uint8_t* g = digits[d - 1];
    for (int c = 0; c < 5; c++) {
        uint8_t bits = g[c];
        for (int r = 0; r < 7; r++)
            if (bits & (1 << r)) setPixel(x + c, y + r, col);
    }
}

const uint8_t letters[][5] = {
    {0x7F,0x09,0x09,0x09,0x06},
    {0x7C,0x0A,0x09,0x0A,0x7C},
    {0x7F,0x09,0x19,0x29,0x46},
    {0x26,0x49,0x49,0x49,0x32},
};
const int parsa[] = {0,1,2,3,1};

void drawParsa(int ox, int oy, uint16_t col) {
    for (int i = 0; i < 5; i++) {
        const uint8_t* g = letters[parsa[i]];
        for (int c = 0; c < 5; c++) {
            uint8_t bits = g[c];
            for (int r = 0; r < 7; r++)
                if (bits & (1 << r)) setPixel(ox + i * 6 + c, oy + r, col);
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(500);

    HUB75_I2S_CFG cfg(PHYS_PPW, PHYS_PPH, PANELS);
    cfg.driver          = HUB75_I2S_CFG::SHIFTREG;
    cfg.clkphase        = false;
    cfg.latch_blanking  = 4;
    cfg.i2sspeed        = HUB75_I2S_CFG::HZ_8M;
    cfg.min_refresh_rate = 30;  // allow lower refresh to reduce noise

    // Reduce colour depth to 3 bits — less data, cleaner signal
    cfg.setPixelColorDepthBits(3);

    dma = new MatrixPanel_I2S_DMA(cfg);
    if (!dma->begin()) {
        Serial.println("DMA init failed");
        while (true) delay(1000);
    }
    dma->setBrightness8(40);
    dma->clearScreen();

    Serial.println("=== 4-PANEL ANTI-NOISE TEST ===");
    Serial.printf("Clock: 8MHz, Blanking: 4, ColorDepth: 3bit\n");
    Serial.printf("Refresh: %d Hz\n\n", dma->calculated_refresh_rate);
}

int testNum = 0;

void loop() {
    uint16_t red = dma->color565(255, 0, 0);
    uint16_t dim = dma->color565(40, 0, 0);

    switch (testNum) {

        case 0: {
            Serial.println("TEST 1: One panel at a time");
            for (int p = 0; p < PANELS; p++) {
                clearAll();
                int x0 = p * PANEL_W;
                fillRect(x0, 0, PANEL_W, PANEL_H, dim);
                drawRect(x0, 0, PANEL_W, PANEL_H, red);
                drawDigit(x0 + 13, 5, p + 1, red);
                Serial.printf("  Panel %d\n", p + 1);
                delay(2000);
            }
            break;
        }

        case 1: {
            Serial.println("TEST 2: All panels numbered");
            clearAll();
            for (int p = 0; p < PANELS; p++) {
                int x0 = p * PANEL_W;
                drawRect(x0, 0, PANEL_W, PANEL_H, red);
                drawDigit(x0 + 13, 5, p + 1, red);
            }
            delay(5000);
            break;
        }

        case 2: {
            Serial.println("TEST 3: Line sweep");
            for (int x = 0; x < LOG_W; x++) {
                clearAll();
                for (int y = 0; y < LOG_H; y++)
                    setPixel(x, y, red);
                delay(15);
            }
            break;
        }

        case 3: {
            Serial.println("TEST 4: Scrolling PARSA");
            for (int offset = LOG_W; offset > -36; offset--) {
                clearAll();
                drawParsa(offset, 5, red);
                delay(20);
            }
            break;
        }
    }

    testNum = (testNum + 1) % 4;
}