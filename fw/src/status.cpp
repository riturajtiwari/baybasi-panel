#include "status.h"
// rgbLedWrite(), not neopixelWrite(). Identical signature, but arduino-esp32
// 3.x deprecated the old name and warns on EVERY call - and this runs every
// 40 ms, which buried the boot log under 400 warnings in 16 seconds the first
// time this firmware ran. 2026-09-19.
#include "config.h"

namespace {
status::State g_state = status::State::Booting;
uint32_t g_identifyUntil = 0;
uint32_t g_last = 0;
uint8_t g_phase = 0;
}  // namespace

namespace status {

void begin() {
    rgbLedWrite(PIN_STATUS, 24, 0, 0);
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
        rgbLedWrite(PIN_STATUS, on ? 120 : 0, on ? 120 : 0, on ? 120 : 0);
        return;
    }

    const uint8_t slow = (g_phase / 12) & 1;    // ~1 Hz
    const uint8_t fast = (g_phase / 3) & 1;     // ~4 Hz
    // A triangle, so "running" breathes instead of blinking: a blinking LED in
    // the corner of your eye reads as a fault.
    const uint8_t breathe = (g_phase & 0x40) ? (uint8_t)(63 - (g_phase & 0x3f))
                                             : (uint8_t)(g_phase & 0x3f);

    switch (g_state) {
        case State::Booting:   rgbLedWrite(PIN_STATUS, 24, 0, 0); break;
        case State::NoLink:    rgbLedWrite(PIN_STATUS, slow ? 40 : 0, 0, 0); break;
        case State::NoSignal:  rgbLedWrite(PIN_STATUS, 30, 14, 0); break;
        case State::Buffering: rgbLedWrite(PIN_STATUS, 0, 0, 40); break;
        case State::Running:   rgbLedWrite(PIN_STATUS, 0, 3 + breathe / 8, 0); break;
        case State::Torn:      rgbLedWrite(PIN_STATUS, 30, 0, 30); break;
        case State::Updating:  rgbLedWrite(PIN_STATUS, breathe, breathe, breathe); break;
        case State::Identify:  rgbLedWrite(PIN_STATUS, 120, 120, 120); break;
        case State::Fault:     rgbLedWrite(PIN_STATUS, fast ? 90 : 0, 0, 0); break;
    }
}

}  // namespace status
