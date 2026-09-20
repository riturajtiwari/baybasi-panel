#include "leds.h"

// FastLED, not I2SClocklessLedDriver.
//
// hpwit's driver compiled against ESP-IDF 5.5 but did not work: showPixels()
// took ~1 s per frame against a predicted 7.68 ms, so of 645 frames assembled
// at a clean 30 fps only 4 ever reached the panel. The data was correct - the
// panel showed the right colours - purely the rate was wrong. Two smells said
// IDF mismatch before the measurement did: the library needs
// gdma_channel_alloc_config_t::flags::isr_cache_safe (IDF 5.4+) and calls
// memset() without including <string.h>.
//
// FastLED wraps the same class of S3 LCD_CAM driver but tracks which IDF
// versions it misbehaves on and refuses to build on them - see the guards at
// the top of platforms/esp/32/clockless_i2s_esp32s3.h, which hard error on
// 5.1.x and 5.3.2 and tell you to move to 5.4+. We are on 5.5.5.
//
// -DFASTLED_USES_ESP32S3_I2S in platformio.ini is what selects it: it makes
// WS2812Controller800Khz resolve to ClocklessController_I2S_Esp32_WS2812, so
// all twelve addLeds() outputs clock out together through LCD_CAM instead of
// queueing on the S3's four RMT channels. A frame then costs one strand's time.
#include <FastLED.h>

namespace {

bool g_enabled = false;
uint8_t g_scratch[FRAME_BYTES];

// CRGB is three bytes, so the frame buffer IS a CRGB array - no copy, no second
// 9 KB allocation. Output n owns the slice starting at n * PANEL_LEDS.
CRGB *const g_leds = reinterpret_cast<CRGB *>(g_scratch);

}  // namespace

namespace leds {

void begin() {
    // Before anything else can drive GPIO 8: HIGH means the shifters are
    // high-impedance. The board's 10k to 3V3E already holds it there through
    // boot; this makes sure nothing later pulls it low by accident.
    pinMode(PIN_OE, OUTPUT);
    digitalWrite(PIN_OE, HIGH);
    g_enabled = false;

    memset(g_scratch, 0, sizeof(g_scratch));

    // RGB here, and ALL the channel mapping in config.h's CHANNEL_MAP. Ask
    // FastLED to reorder as well and you get two transforms to reason about;
    // with one, the fix for a wrong colour is always the same one line.
    // CHANNEL_MAP was measured on hardware - see the note there before
    // touching either it or these template arguments.
    //
    // Pin numbers are template arguments, so the twelve are written out. They
    // must match LED_PINS in config.h.
    FastLED.addLeds<WS2812B,  4, RGB>(&g_leds[ 0 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B,  5, RGB>(&g_leds[ 1 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B,  6, RGB>(&g_leds[ 2 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B,  1, RGB>(&g_leds[ 3 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B,  2, RGB>(&g_leds[ 4 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 21, RGB>(&g_leds[ 5 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 38, RGB>(&g_leds[ 6 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 39, RGB>(&g_leds[ 7 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 40, RGB>(&g_leds[ 8 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 41, RGB>(&g_leds[ 9 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 42, RGB>(&g_leds[10 * PANEL_LEDS], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 47, RGB>(&g_leds[11 * PANEL_LEDS], PANEL_LEDS);

    // Brightness is done on the Pi, in 16 bit, before dithering. Anything
    // other than full scale here would quantise it a second time.
    FastLED.setBrightness(255);
    FastLED.clear(true);

    log_i("LED driver up (FastLED S3/I2S): %d outputs x %d LEDs = %d px, "
          "%u bytes/frame", NUM_OUTPUTS, PANEL_LEDS, NUM_LEDS,
          (unsigned)FRAME_BYTES);
}

void show(const uint8_t *frame) {
    // Copied in rather than handed over: the caller's buffer is free again the
    // moment this returns. FastLED.show() is synchronous and returns when the
    // last bit is on the wire, so there is no in-flight buffer to protect.
    memcpy(g_scratch, frame, FRAME_BYTES);
    FastLED.show();
}

// Kept so main.cpp's first-frame sequence still reads the same. FastLED.show()
// already blocks, so by the time anyone calls this there is nothing to wait for.
void waitDone() {}

void enableOutputs() {
    if (g_enabled) return;
    digitalWrite(PIN_OE, LOW);
    g_enabled = true;
    log_i("level shifters enabled; the panels are live");
}

void disableOutputs() {
    digitalWrite(PIN_OE, HIGH);
    g_enabled = false;
}

bool outputsEnabled() { return g_enabled; }

void fadeStep(uint8_t *frame, uint8_t shift) {
    for (size_t i = 0; i < FRAME_BYTES; i++) {
        const uint8_t v = frame[i];
        frame[i] = (uint8_t)(v - (v >> shift) - (v ? 1 : 0));
    }
}

void blackOut(uint8_t *frame) { memset(frame, 0, FRAME_BYTES); }

}  // namespace leds
