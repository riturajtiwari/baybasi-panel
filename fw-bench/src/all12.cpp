// Baybasi — all twelve outputs at once, for controller board bring-up.
//
//   pio run -e ctrl-all12 -t upload
//
// Every output runs the same walking-trail pattern in its OWN colour, and parks
// N white pixels at the head of the chain where N is the output number. So you
// flash once, then move a single panel from J1 to J12 and read off which output
// you are actually on. Plug into J7 and see six white pixels and you have found
// a wiring error, not a dead output.
//
// The trail walks the chain in RAW ORDER, index 0 to 255, deliberately. On a
// column-serpentine panel that draws a clean boustrophedon: up column 0, down
// column 1, up column 2. If it scribbles instead, the panel is not wired the way
// ../fw and ../../sw assume, and that assumption has never been checked against
// hardware. This is the check.
//
// POWER. Only ~20 pixels light per output, so one panel draws under half an amp
// at the default brightness. FastLED's power limiter is deliberately NOT used:
// it would size itself to all twelve 256-LED buffers, decide 3 072 LEDs were at
// risk, and dim the one panel you actually connected down to nothing. Brightness
// is fixed instead, which is predictable. If you ever hang several panels on this
// at once, multiply: 20 px x 60 mA x brightness/255, per panel.

#include <Arduino.h>
#include <FastLED.h>

#define PANEL_W 16
#define PANEL_H 16
#define PANEL_LEDS (PANEL_W * PANEL_H)
#define N_OUT 12

#ifndef OE_PIN
#define OE_PIN 8          // LOW enables both SN74AHCT245s. Nothing leaves the board until it is.
#endif
#ifndef BRIGHTNESS
#define BRIGHTNESS 96     // 20 lit px x 60 mA x 96/255 = ~0.45 A for one panel
#endif
#ifndef WALK_MS
#define WALK_MS 12000     // one full traverse of a panel
#endif
#define TRAIL 8           // lit pixels in the moving trail

// D1..D12 in board order. Taken from FABRICATION.md's pin map; the first three
// are on the devkit's LEFT header, the other nine on the RIGHT.
static const uint8_t PIN_OF[N_OUT] = {4, 5, 6, 1, 2, 21, 38, 39, 40, 41, 42, 47};

CRGB leds[N_OUT][PANEL_LEDS];

void setup() {
    Serial.begin(115200);
    // Native USB CDC enumerates AFTER the sketch starts, so anything printed in
    // the first ~1 s is thrown away and you attach the monitor to an empty
    // terminal. Wait for the host to open the port, but never block forever:
    // this firmware has to run standalone with nothing attached.
    for (uint32_t t0 = millis(); !Serial && millis() - t0 < 2500; ) delay(10);

    // Park every data line low BEFORE enabling the buffers. A 245 is a buffer,
    // not a latch: enable it while its inputs are still floating ESP32 pads and
    // it drives that float straight at a panel's DIN.
    for (uint8_t i = 0; i < N_OUT; i++) {
        pinMode(PIN_OF[i], OUTPUT);
        digitalWrite(PIN_OF[i], LOW);
    }
    pinMode(OE_PIN, OUTPUT);
    digitalWrite(OE_PIN, LOW);

    // Pin numbers must be compile-time constants, so these are written out.
    FastLED.addLeds<WS2812B,  4, GRB>(leds[0],  PANEL_LEDS);
    FastLED.addLeds<WS2812B,  5, GRB>(leds[1],  PANEL_LEDS);
    FastLED.addLeds<WS2812B,  6, GRB>(leds[2],  PANEL_LEDS);
    FastLED.addLeds<WS2812B,  1, GRB>(leds[3],  PANEL_LEDS);
    FastLED.addLeds<WS2812B,  2, GRB>(leds[4],  PANEL_LEDS);
    FastLED.addLeds<WS2812B, 21, GRB>(leds[5],  PANEL_LEDS);
    FastLED.addLeds<WS2812B, 38, GRB>(leds[6],  PANEL_LEDS);
    FastLED.addLeds<WS2812B, 39, GRB>(leds[7],  PANEL_LEDS);
    FastLED.addLeds<WS2812B, 40, GRB>(leds[8],  PANEL_LEDS);
    FastLED.addLeds<WS2812B, 41, GRB>(leds[9],  PANEL_LEDS);
    FastLED.addLeds<WS2812B, 42, GRB>(leds[10], PANEL_LEDS);
    FastLED.addLeds<WS2812B, 47, GRB>(leds[11], PANEL_LEDS);

    FastLED.setBrightness(BRIGHTNESS);
    FastLED.clear(true);

    Serial.println(F("\n=== Baybasi controller board — all 12 outputs ==========="));
    Serial.printf("  /OE on GPIO %d driven LOW: both 245s enabled\n", OE_PIN);
    Serial.println(F("  Move ONE panel J1 -> J12. Each output shows:"));
    Serial.println(F("    - N white pixels at the head of the chain, N = output number"));
    Serial.println(F("    - a coloured trail walking the chain in raw order"));
    Serial.println(F("  A clean up-down-up sweep confirms the column-serpentine map."));
    for (uint8_t i = 0; i < N_OUT; i++)
        Serial.printf("    D%-2d  GPIO %-2d  ->  J%d\n", i + 1, PIN_OF[i], i + 1);
    Serial.printf("  Brightness %d, ~%.2f A for one panel.\n",
                  BRIGHTNESS, 20 * 0.060f * BRIGHTNESS / 255.0f);
    Serial.println(F("========================================================="));
}

void loop() {
    const uint32_t step = WALK_MS / PANEL_LEDS;
    uint32_t head = (millis() / (step ? step : 1)) % (PANEL_LEDS + TRAIL);

    for (uint8_t o = 0; o < N_OUT; o++) {
        fill_solid(leds[o], PANEL_LEDS, CRGB::Black);

        // identity: N white pixels at the head of the chain
        for (uint8_t k = 0; k <= o && k < PANEL_LEDS; k++) leds[o][k] = CRGB::White;

        // trail, in this output's own hue
        CHSV hue(o * 21, 255, 255);
        for (uint8_t t = 0; t < TRAIL; t++) {
            int32_t i = (int32_t)head - t;
            if (i < 0 || i >= PANEL_LEDS) continue;
            CRGB c = hue;
            c.nscale8(255 - t * (200 / TRAIL));
            leds[o][i] = c;
        }
    }
    FastLED.show();

    // Heartbeat. The banner is printed once and is easily missed; this means a
    // monitor attached at any time tells you the firmware is alive, what the
    // walk is doing, and that /OE is still held low.
    static uint32_t beat = 0;
    if (millis() - beat >= 3000) {
        beat = millis();
        Serial.printf("[%5lus] alive  head %3lu/%d  /OE=%d  brightness %d\n",
                      (unsigned long)(millis() / 1000), (unsigned long)head,
                      PANEL_LEDS, digitalRead(OE_PIN), BRIGHTNESS);
    }
}
