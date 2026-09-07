#include "status.h"
#include "config.h"

namespace {
status::State g_state = status::State::Booting;
uint32_t g_identifyUntil = 0;
uint32_t g_last = 0;
uint8_t g_phase = 0;
}  // namespace

namespace status {

void begin() {
    neopixelWrite(PIN_STATUS, 24, 0, 0);
    g_state = State::Booting;
}

void set(State s) { g_state = s; }
State get() { return g_state; }

void identify(uint32_t ms) { g_identifyUntil = millis() + ms; }

void tick() {
    const uint32_t now = millis();
    if (now - g_last < 40) return;
    g_last = now;
    g_phase++;

    if (now < g_identifyUntil) {
        const bool on = (g_phase / 3) & 1;
        neopixelWrite(PIN_STATUS, on ? 120 : 0, on ? 120 : 0, on ? 120 : 0);
        return;
    }

    const uint8_t slow = (g_phase / 12) & 1;    // ~1 Hz
    const uint8_t fast = (g_phase / 3) & 1;     // ~4 Hz
    // A triangle, so "running" breathes instead of blinking: a blinking LED in
    // the corner of your eye reads as a fault.
    const uint8_t breathe = (g_phase & 0x40) ? (uint8_t)(63 - (g_phase & 0x3f))
                                             : (uint8_t)(g_phase & 0x3f);

    switch (g_state) {
        case State::Booting:   neopixelWrite(PIN_STATUS, 24, 0, 0); break;
        case State::NoLink:    neopixelWrite(PIN_STATUS, slow ? 40 : 0, 0, 0); break;
        case State::NoSignal:  neopixelWrite(PIN_STATUS, 30, 14, 0); break;
        case State::Buffering: neopixelWrite(PIN_STATUS, 0, 0, 40); break;
        case State::Running:   neopixelWrite(PIN_STATUS, 0, 3 + breathe / 8, 0); break;
        case State::Torn:      neopixelWrite(PIN_STATUS, 30, 0, 30); break;
        case State::Updating:  neopixelWrite(PIN_STATUS, breathe, breathe, breathe); break;
        case State::Identify:  neopixelWrite(PIN_STATUS, 120, 120, 120); break;
        case State::Fault:     neopixelWrite(PIN_STATUS, fast ? 90 : 0, 0, 0); break;
    }
}

}  // namespace status
