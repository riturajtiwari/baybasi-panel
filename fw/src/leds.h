#pragma once
#include <Arduino.h>
#include "config.h"

// The twelve parallel WS2812B outputs, and the level-shifter enable.
//
// The ESP32-S3 has only four RMT transmit channels, so twelve simultaneous
// outputs go through the LCD_CAM peripheral in parallel mode.  Any GPIO works
// because it routes through the GPIO matrix.
//
// All twelve run at once, so a frame costs one strand's time - 256 LEDs at
// 30 us is 7.68 ms, plus a 300 us latch budget that covers both the 50 us and
// 280 us WS2812B variants.  7.98 ms is a 125 fps ceiling against a 30 fps
// target, which is where the headroom comes from.

namespace leds {

void begin();

// Push a 9216-byte buffer, already in LED channel order.  Non-blocking: the
// LED peripheral clocks it out by DMA while the CPU goes back to the network.
void show(const uint8_t *frame);

// Block until the current transmission has finished.
void waitDone();

// The level shifters.  /OE is HIGH (outputs high-impedance) from reset, held
// there by the board's pull-up to 3V3E, and the panels see a defined low
// through the per-output pull-downs.  It is driven LOW only once a complete
// frame has been buffered and clocked out, so the wall cannot show noise at
// power-up.
void enableOutputs();
void disableOutputs();
bool outputsEnabled();

// Fade the held frame towards black.  Called while no packets are arriving.
void fadeStep(uint8_t *frame, uint8_t shift);
void blackOut(uint8_t *frame);

}  // namespace leds
