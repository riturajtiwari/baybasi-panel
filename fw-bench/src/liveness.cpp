// Baybasi — single-panel liveness check, no controller PCB, no bench supply.
//
//   pio run -e panel-liveness -t upload
//
// For walking a built wall and finding panels that need replacing. The devkit
// powers the panel from its own 5 V pin and drives DIN directly: one USB cable
// and one 3-pin lead, repeated 48 times.
//
// Wiring, and the order matters:
//
//   devkit 14    -> panel DIN  (green)
//   devkit 5Vin  -> panel +5 V (red)
//   devkit GND   -> panel GND  (white)     <- connect FIRST, remove LAST
//
// Contiguous at the bottom of the left header, in the order DATA / 5V / GND.
// A standard WS2812 lead has DATA in the middle, so the test lead is
// deliberately re-ordered to come out right at the panel. LABEL IT - it is
// wired differently from every other lead in this project.
//
// GND first and out last is not fussiness. Data into a panel whose 5 V is off
// back-powers it through the DIN clamp diode and sinks the whole panel's
// wake-up current into one GPIO. That has already cost this project a pin.
//
// ---------------------------------------------------------------------------
// CURRENT BUDGET — the reason this pattern is shaped the way it is
//
// 256 WS2812Bs at full white is 15.4 A. Irrelevant here; what matters is that
// USB gives you around 0.5 A on an old port and 1.5-3 A from a charger, and
// the devkit's own VBUS trace and polyfuse sit in the way.
//
// The floor is not the pattern, it is the panel: every WS2812B draws roughly
// 0.6-1 mA just to run its controller, so 256 of them idle at ~150-260 mA
// before a single LED lights. Add ~80 mA for the devkit and you have spent
// half a 500 mA budget doing nothing.
//
// So nothing here lights the whole panel in white. The sweeps light a handful
// of LEDs at a time and cover all 256 over a second or two; the floods light
// every LED but in ONE channel at a low level. FastLED's power limiter is set
// as a hard backstop - unlike all12.cpp, which had to disable it because it
// sized itself to twelve panel buffers, here there is exactly one panel and
// the limiter models it correctly.
//
// Estimated worst case: MAX_MA (drive) + ~260 mA (quiescent) + ~80 mA (devkit).
// At the default 400 mA that is ~740 mA, so use a charger or a powered hub,
// NOT an old 500 mA USB-A port.
// ---------------------------------------------------------------------------
//
// WHAT EACH PHASE FINDS
//
//   1 chain   one white pixel walks 0 -> 255. Where it stops is where the
//             chain breaks. A gap means one dead pixel. This is the test that
//             actually matters, and it is nearly free in current.
//   2 band    an 8-pixel bar sweeps the panel in pure red, then green, then
//             blue. Every LED is driven on every channel, so a pixel with one
//             dead colour shows up as the wrong colour passing through.
//   3 flood   every LED on, one channel at a time, dim. A dead pixel is an
//             obvious dark dot without having to watch a sweep go by.
//
// A panel that passes all three is good. A panel that fails is SUSPECT, not
// condemned - read the note on 3.3 V signalling in the README before you throw
// one away.

#include <Arduino.h>
#include <FastLED.h>

#ifndef LED_PIN
#define LED_PIN 14
#endif
#ifndef PANEL_LEDS
#define PANEL_LEDS 256
#endif
#ifndef MAX_MA
#define MAX_MA 400          // FastLED drive budget, excludes quiescent
#endif
#ifndef SWEEP_LEVEL
#define SWEEP_LEVEL 96      // only a few LEDs lit, so this can be bright
#endif
#ifndef FLOOD_LEVEL
#define FLOOD_LEVEL 12      // ALL 256 lit: 256 * 20 mA * 12/255 = ~240 mA
#endif
#ifndef STATUS_LED
#define STATUS_LED 48
#endif

namespace {

CRGB g_leds[PANEL_LEDS];

constexpr uint16_t BAND      = 8;      // pixels in the sweeping bar
constexpr uint32_t STEP_MS   = 7;      // per sweep step: 256 * 7 = ~1.8 s
constexpr uint32_t FLOOD_MS  = 1000;
constexpr uint32_t REST_MS   = 600;

enum class Phase : uint8_t {
    Chain, BandR, BandG, BandB, FloodR, FloodG, FloodB, Rest
};

Phase    g_phase = Phase::Chain;
uint16_t g_step  = 0;
uint32_t g_last  = 0;
uint32_t g_cycle = 0;

const char *phaseName(Phase p) {
    switch (p) {
        case Phase::Chain:  return "chain sweep  (watch where it stops)";
        case Phase::BandR:  return "band RED";
        case Phase::BandG:  return "band GREEN";
        case Phase::BandB:  return "band BLUE";
        case Phase::FloodR: return "flood RED    (look for dark pixels)";
        case Phase::FloodG: return "flood GREEN  (look for dark pixels)";
        case Phase::FloodB: return "flood BLUE   (look for dark pixels)";
        default:            return "rest";
    }
}

// Colour for the sweeping band, by phase.
CRGB bandColour(Phase p) {
    switch (p) {
        case Phase::BandR: return CRGB(SWEEP_LEVEL, 0, 0);
        case Phase::BandG: return CRGB(0, SWEEP_LEVEL, 0);
        case Phase::BandB: return CRGB(0, 0, SWEEP_LEVEL);
        default:           return CRGB(SWEEP_LEVEL, SWEEP_LEVEL, SWEEP_LEVEL);
    }
}

CRGB floodColour(Phase p) {
    switch (p) {
        case Phase::FloodR: return CRGB(FLOOD_LEVEL, 0, 0);
        case Phase::FloodG: return CRGB(0, FLOOD_LEVEL, 0);
        default:            return CRGB(0, 0, FLOOD_LEVEL);
    }
}

void advance() {
    g_step = 0;
    switch (g_phase) {
        case Phase::Chain:  g_phase = Phase::BandR;  break;
        case Phase::BandR:  g_phase = Phase::BandG;  break;
        case Phase::BandG:  g_phase = Phase::BandB;  break;
        case Phase::BandB:  g_phase = Phase::FloodR; break;
        case Phase::FloodR: g_phase = Phase::FloodG; break;
        case Phase::FloodG: g_phase = Phase::FloodB; break;
        case Phase::FloodB: g_phase = Phase::Rest;   break;
        case Phase::Rest:
            g_phase = Phase::Chain;
            g_cycle++;
            Serial.printf("\n--- cycle %lu -------------------------------\n",
                          (unsigned long)g_cycle);
            break;
    }
    Serial.printf("  %s\n", phaseName(g_phase));
}

}  // namespace

void setup() {
    Serial.begin(115200);
    delay(400);

    FastLED.addLeds<WS2812B, LED_PIN, GRB>(g_leds, PANEL_LEDS);
    // Hard backstop on drive current. With one panel the limiter models the
    // load correctly, so a mistyped level cannot pull more than this.
    FastLED.setMaxPowerInVoltsAndMilliamps(5, MAX_MA);
    FastLED.setBrightness(255);       // levels are set per pixel, not globally
    FastLED.clear(true);

    Serial.printf(
        "\n=== Baybasi panel liveness =================================\n"
        "  %d LEDs on GPIO %d,  drive capped at %d mA\n"
        "  expect ~%d mA total: %d drive + ~260 quiescent + ~80 devkit\n"
        "  USE A CHARGER OR POWERED HUB, not a 500 mA USB-A port.\n"
        "\n"
        "  PASS = the chain sweep reaches the last pixel with no gaps,\n"
        "         and all three floods are even with no dark dots.\n"
        "  FAIL = suspect, NOT condemned. Re-test through the controller\n"
        "         board before discarding - see the 3.3 V note in README.\n"
        "============================================================\n",
        PANEL_LEDS, LED_PIN, MAX_MA, MAX_MA + 340, MAX_MA);
    Serial.printf("  %s\n", phaseName(g_phase));
    g_last = millis();
}

void loop() {
    const uint32_t now = millis();

    switch (g_phase) {
        case Phase::Chain:
        case Phase::BandR:
        case Phase::BandG:
        case Phase::BandB: {
            if (now - g_last < STEP_MS) return;
            g_last = now;
            const uint16_t width = (g_phase == Phase::Chain) ? 1 : BAND;
            fill_solid(g_leds, PANEL_LEDS, CRGB::Black);
            const CRGB c = bandColour(g_phase);
            for (uint16_t k = 0; k < width; k++) {
                const int idx = (int)g_step - (int)k;
                if (idx >= 0 && idx < PANEL_LEDS) g_leds[idx] = c;
            }
            FastLED.show();
            // Run past the end so the tail of the band clears the last pixel -
            // otherwise a break in the final few LEDs hides behind the band.
            if (++g_step >= PANEL_LEDS + width) advance();
            break;
        }

        case Phase::FloodR:
        case Phase::FloodG:
        case Phase::FloodB: {
            if (g_step == 0) {
                fill_solid(g_leds, PANEL_LEDS, floodColour(g_phase));
                FastLED.show();
                g_step = 1;
                g_last = now;
            } else if (now - g_last >= FLOOD_MS) {
                advance();
            }
            break;
        }

        case Phase::Rest: {
            if (g_step == 0) {
                FastLED.clear(true);
                g_step = 1;
                g_last = now;
            } else if (now - g_last >= REST_MS) {
                advance();
            }
            break;
        }
    }
}
