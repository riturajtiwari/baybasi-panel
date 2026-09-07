#include "leds.h"
#include "I2SClocklessLedDriver.h"

namespace {
I2SClocklessLedDriver g_driver;
int g_pins[NUM_OUTPUTS];
bool g_enabled = false;
bool g_busy = false;
uint8_t g_scratch[FRAME_BYTES];
}  // namespace

namespace leds {

void begin() {
    // Do this before anything else can drive GPIO 8: HIGH means the shifters
    // are high-impedance.  The board's 10k to 3V3E already holds it there
    // through boot; this just makes sure nothing later pulls it low by accident.
    pinMode(PIN_OE, OUTPUT);
    digitalWrite(PIN_OE, HIGH);
    g_enabled = false;

    for (int i = 0; i < NUM_OUTPUTS; i++) g_pins[i] = LED_PINS[i];

    memset(g_scratch, 0, sizeof(g_scratch));
    g_driver.initled(g_scratch, g_pins, NUM_OUTPUTS, PANEL_LEDS);

    // Brightness is done on the Pi, in 16 bit, before dithering.  Anything
    // other than full scale here would quantise it a second time.
    g_driver.setBrightness(255);

    log_i("LED driver up: %d outputs x %d LEDs = %d px, %u bytes/frame",
          NUM_OUTPUTS, PANEL_LEDS, NUM_LEDS, (unsigned)FRAME_BYTES);
}

void show(const uint8_t *frame) {
    if (g_busy) waitDone();
    // The driver's DMA reads from its own buffer for the whole 7.98 ms, so the
    // frame is copied in rather than handed over: the caller's buffer is free
    // again the moment this returns.
    memcpy(g_scratch, frame, FRAME_BYTES);
    g_busy = true;
    g_driver.showPixels(NO_WAIT);
}

void waitDone() {
    if (!g_busy) return;
    g_driver.waitDisplay();
    g_busy = false;
}

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
